# Cash Reconciliation Domain and Integrations Study

> Scope: bank/cash reconciliation as ReconMatch’s first production vertical. This makes source contracts, operational states, and controls concrete before broader payment/securities domains.

## 1. Cash domain model

Cash reconciliation compares independent views of account activity: bank-reported entries/balances, internal cashbook/ERP postings, payment instructions/statuses, and optionally treasury forecasts. It must distinguish:

| State | Meaning | May auto-match to final cash? |
|---|---|---|
| Instruction created | Internal intent to move money. | No; it may never be submitted. |
| Accepted / rejected | Bank/rail processing decision. | No; status is not booking. |
| Pending | Expected but not final account movement. | Only as an in-transit relation. |
| Booked | Entry posted to bank account. | Yes, subject to rule. |
| Value dated | Funds economic value date. | Used for interest/cash position, may differ from booking. |
| Returned/reversed | Original movement was undone or rejected. | Link to original, never as unrelated payment. |

ISO 20022 distinguishes payment initiation (`pain`), clearing/settlement (`pacs`), cash reporting (`camt`), and remittance (`remt`). [ISO business areas](https://www.iso20022.org/sites/default/files/documents/D7/ISO20022_BusinessAreas.pdf) A `camt.053` statement reports booked entries and balances; it may contain underlying transaction detail and is explicitly for cash management/reconciliation. [ISO camt.053 definition](https://www.iso20022.org/sites/default/files/documents/messages/mdr_part_2/ISO20022_MDRPart2_BankToCustomerCashManagement_2018_2019_v1_0.pdf)

## 2. Source adapter contract

Every bank/ERP adapter implements the same pipeline:

```text
authenticate -> receive -> preserve bytes -> identify/idempotency -> parse -> validate
             -> canonicalize -> control totals -> publish immutable record versions
```

| Stage | Mandatory behavior |
|---|---|
| Receive | Use least-privilege credentials; capture source/message/file identifier and receipt timestamp. |
| Evidence | Calculate content hash before parsing; store encrypted immutable object. |
| Idempotency | Detect retransmission by source ID + content/hash/version semantics; record duplicate delivery decision. |
| Parse | Pin parser/schema/mapping version; preserve unknown source fields where feasible. |
| Validate | Validate required fields, dates, decimal/currency, account ownership, debit/credit direction, duplicate source record IDs. |
| Canonicalize | Explicit sign, timezone, date, currency, reference, and narrative transformations. |
| Control | Compute count/debit/credit totals; reconcile stated balances/headers when supplied. |
| Publish | Write immutable canonical version and ingestion events atomically/idempotently. |

No adapter may call the matching engine with rows that bypass the evidence and validation steps.

## 3. Minimum canonical mapping

| Canonical field | CSV input | ISO 20022 guidance | Notes |
|---|---|---|---|
| Source identity | file name + row / supplied ID | message/header + statement/entry reference | A source ID alone may not be globally unique. |
| Account | optional CSV metadata | account identification | Partition and authorize by account. |
| Booking date | `date` | entry booking date | Default matching date for booked cash. |
| Value date | optional | value date | Preserve separately. |
| Amount / direction | signed `amount` | amount + credit/debit indicator | Record raw and canonical sign mapping. |
| Currency | configured default/CSV | account/transaction currency | Never assume for multi-currency source. |
| Reference IDs | `reference` | entry/transaction/end-to-end references | Keep typed list, not one lossy string. |
| Narrative/remittance | `description` | additional entry info/remittance | Preserve raw plus versioned normalized form. |
| Status | absent in current CSV | pending/booked/status data | Do not invent booked status. |
| Balance | absent in current CSV | opening/interim/closing balance | Enables population/balance control. |

Banks frequently vary optional field population and proprietary transaction codes; an adapter must use a per-bank mapping contract, test corpus, and change process. ISO external code sets update independently of message schemas, so reference-code versions also need tracking. [ISO external code sets](https://www.iso20022.org/catalogue/additional-content-messages/external-code-sets?trk=public_post_comment-text)

## 4. Reconciliation definitions for cash

A definition is not merely two file names. Store and approve:

```text
name, owner, legal entity, bank accounts, internal books,
sources and expected schedule, business calendar/cut-off,
currency/sign policy, matching-rule versions, fee/timing policies,
materiality, SLA/escalation, preparer/reviewer, retention and close policy
```

### Population controls

For each account/business date report:

```text
expected source partitions; received/duplicate/late/missing partitions;
record count; debit total; credit total; opening balance; closing balance;
quarantined rows; eligible records; matched/unmatched/in-transit totals
```

Required cash balance check when statement balances are present:

```text
opening balance + booked credits + booked debits = closing balance
```

The reconciliation must stop or visibly degrade if this fails. A match rate cannot compensate for an unproven bank population.

## 5. Matching rules and expected differences

| Scenario | Safe baseline | Difference handling |
|---|---|---|
| Payment instruction -> bank debit | End-to-end/payment reference, account, currency, signed amount, booking/value policy | In transit until booked; do not consume final entry early. |
| Customer receipt -> ERP cash | Remittance/reference + amount/date + payer | Support 1:N invoice allocation; unidentified receipt becomes case. |
| Payroll/bulk supplier debit | Batch ID/control total + N:1 exact allocation | Do not use employee/supplier narrative similarity as proof. |
| Bank fee / interest | Bank transaction code + approved GL mapping | Create/approve ledger entry; never silently net against payment. |
| Returned payment | Original reference/status/reason/time | Reverse/link original chain; preserve return reason. |
| FX payment | Instructed and settled amount/currency + rate/fee model | Explain each component; no generic percentage tolerance. |
| Cash-pool sweep | Entity/account/sweep reference + controlled allocation | Enforce legal-entity/intercompany policy. |

### Tolerances

Allow only named policies, e.g. `BANK_ROUNDING_MINOR_UNIT_V1` or `CORRESPONDENT_FEE_V2`, with scope, bounds, effective dates, owner, accounting treatment, and monitoring. A universal 1% tolerance is not a cash-control policy.

## 6. Operational failures and recovery

| Failure | Detection | Safe recovery |
|---|---|---|
| File absent/late | Expected schedule/cut-off check | Hold attestation; retry or escalate, never substitute prior file silently. |
| Duplicate delivery | Message/file/source ID and content hash | Record duplicate; do not create new economics. |
| Corrected bank statement | New evidence/version or explicit correction marker | Preserve prior source; generate correction run and impact list. |
| Parser/schema drift | Contract validation and unknown-field telemetry | Quarantine affected batch; use approved mapper upgrade and replay. |
| Partial load/outage | Atomic batch state/control totals | Retry idempotently from evidence; never partially mark source complete. |
| Matching configuration error | Rule approval, shadow run, precision monitoring | Disable/revert by new version; re-run affected scope with evidence. |

Swift’s cash-management criteria call for technical-message reconciliation, error handling, repair, and retransmission—business reconciliation must not obscure delivery defects. [Swift criteria](https://www2.swift.com/knowledgecentre/rest/v1/publications/s_comp_app_csh_mgt_corp_lbl_crtria_2024/1.0/s_comp_app_csh_mgt_corp_lbl_crtria_2024.pdf?logDownload=true)

## 7. ReconMatch integration sequence

1. Keep existing two-CSV demo but create an internal `SourceBatch`/evidence record for each upload.
2. Add CSV metadata/configuration: entity, account, currency, source system, business date, expected control totals.
3. Create canonical cash records with booking/value date and typed references while retaining current `LedgerEntry`/`StatementLine` adapter for compatibility.
4. Add duplicate source detection, record/totals/balance checks, row quarantine, and replay from retained evidence.
5. Add `camt.053` first; add `camt.054` notifications only with a clear pending/booked lifecycle policy.
6. Add workflow/attestation before enabling automatic journal posting.

## 8. Test corpus

Each adapter needs retained, sanitized golden fixtures for: normal statement, multiple accounts, empty/no-activity statement, duplicate delivery, malformed XML/CSV, negative/positive signs, missing optional references, multi-currency, fees, return/reversal, balance mismatch, late/corrected statement, and bank-specific code change. Test parsed output, control totals, idempotency, and rerun reproducibility.
