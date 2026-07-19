# Industry-Standard Reconciliation Architecture Study

> Purpose: a buildable, vendor-neutral reference architecture for ReconMatch to evolve from a deterministic cash matcher into a controlled reconciliation platform covering cash, payments/cards, securities, GL/subledger, and intercompany. Source IDs refer to the accompanying [source register](2026-07-19-source-register.md).

## Executive conclusion

A production reconciliation system is not a matching algorithm with a dashboard. It is a financial-control system that must prove, for every result, **what source evidence entered, how it was transformed, which versioned rules and configuration ran, why a decision was made, who overrode it, what exception remains, and who attested that the control is complete**.

The durable architecture is a governed pipeline:

```text
Sources -> immutable evidence -> normalize & validate -> reconciliation run
        -> candidate generation -> deterministic decision / review queue
        -> break case & workflow -> attestation / close -> reporting & audit
                                 \-> journals / downstream actions (controlled)
```

Matching automation reduces work; it never substitutes for control design. Basel frames reconciliation as comparing items or outcomes and explaining differences, and expects source reconciliation, validation, exception reporting, data lineage, automation where appropriate, and documented manual workarounds [S06]. Mature public product material consistently adds exception management, approvals/attestation, supporting evidence, journalling, reporting, and audit trails to matching [V02–V05].

## 1. Scope and vocabulary

### 1.1 What reconciliation proves

Reconciliation compares independent or differently produced representations of an economic event, balance, position, or control population. A completed reconciliation proves one of these outcomes:

| Outcome | Meaning | Example |
|---|---|---|
| Matched | Records represent the same economic event(s) under an approved rule. | Bank credit equals ERP cash receipt. |
| Matched with permitted variance | Difference is within a specifically approved model, tolerance, or allocation. | Card settlement net of known merchant fees. |
| In transit | Expected timing difference is tracked with an owner and ageing policy. | Payment initiated but not yet bank-confirmed. |
| Break | A discrepancy requires investigation, correction, escalation, or an adjusting journal. | Bank debit has no ledger item. |
| Not in scope / excluded | Explicitly excluded under versioned, approved policy. | Test account feed excluded from a production recon. |
| Control failure | The recon itself cannot be trusted. | Missing source file, failed balance check, stale reference data, or unapproved configuration change. |

Never label a comparison "reconciled" merely because its current numerical difference is zero. A zero difference can conceal duplicate records, missing populations offset by another error, stale data, an unapproved manual override, or an unresolved timing item.

### 1.2 Reconciliation categories

| Category | Compared populations | Primary object | Typical cadence |
|---|---|---|---|
| Cash / bank | Bank statement, cashbook/ERP, payment file | Cash transaction and closing balance | Intraday, daily, month-end |
| Payments / cards | Authorization, capture, clearing, settlement, payout, fees, chargebacks, safeguarding account | Payment lifecycle / merchant batch | Real-time to daily |
| Securities | Trade, allocation, confirmation, settlement instruction/status, custody position, accounting position | Trade and position/holding | Intraday, T+1, end-of-day |
| GL / subledger | Account balance, subledger detail, supporting schedules, journals | Account substantiation | Month-end / close |
| Intercompany | Entity A receivable/revenue vs entity B payable/expense, eliminations, FX | Bilateral accounting relationship | Daily to month-end |
| Data-integrity / regulatory | Two regulatory or operational representations of the same data | Field/control population | Daily/intraday |

The platform must model both **transaction matching** and **balance substantiation**. The former links granular records; the latter proves a balance from independently sourced support, including reconciling items. Commercial close platforms expose both patterns, not just transaction matching [V01, V02].

### 1.3 Boundary between technical and business reconciliation

These must be separate states with separate owners:

| Layer | Question | Example failure |
|---|---|---|
| Technical delivery | Did the complete, authentic feed arrive once and parse correctly? | Duplicate statement, truncated SFTP file, schema drift. |
| Data quality | Are required fields valid, canonical, and internally consistent? | Invalid currency, bad date, duplicate source ID. |
| Business reconciliation | Do the records/positions/balances agree under approved business policy? | Missing ledger post, fee variance, failed settlement. |
| Control completion | Was the defined process reviewed, evidenced, and signed off on time? | High-risk break untouched after SLA. |

Swift’s corporate criteria explicitly require technical-message reconciliation, error handling, repair, and retransmission; do not let business matching conceal a delivery failure [S04].

## 2. Design principles and non-negotiable invariants

1. **Immutable source evidence.** Preserve the received object, cryptographic checksum, source location/message ID, receipt time, parser version, and retention policy. Do not overwrite it with normalized data.
2. **Reproducible runs.** Every run references frozen input versions, mapping version, reference-data snapshot, rule-set version, engine version, and deterministic seed/ordering. The same inputs must reproduce the same output.
3. **Two-stage data model.** Keep raw/source fields and canonical fields side by side. Normalization is a traceable transformation, not a destructive edit.
4. **No silent mutation.** Corrections, exclusions, overrides, approval decisions, and configuration changes are append-only domain events with actor, reason, before/after state, and evidence.
5. **Completeness before match rate.** Fail or quarantine an incomplete/duplicate/stale population before measuring matching performance. A 99% match rate on an unproven population is not a control.
6. **Determinism first, assistive intelligence second.** Rules decide auto-match eligibility; statistical/AI systems may rank candidates, classify breaks, or draft explanations but must not silently create a financial truth.
7. **Separation of duties by construction.** A user who loads data, changes a rule, or proposes a manual match cannot unilaterally approve the same high-risk result.
8. **Explainability at record level.** A reviewer can see values compared, transformed fields, rule predicates, candidate competitors, tolerance, allocation arithmetic, and why a candidate won or lost.
9. **Minimum necessary data.** Use data minimisation, purpose limitation, retention control, masking, and access scopes. These align with GDPR principles where applicable [S15].
10. **Availability is a financial-control feature.** Define recovery objectives, backlog recovery, late-file handling, cut-off processing, and manual fallback that preserves auditability.

These principles turn Basel’s requirements for governance, accuracy/integrity, completeness, timeliness, adaptability, validation, and exception reporting into product invariants [S06].

## 3. Reference architecture

### 3.1 Logical components

```text
                       +---------------- CONTROL PLANE ----------------+
                       | tenant, roles, policies, rule/version approval |
                       | calendars, materiality, retention, audit query |
                       +---------------------------+-------------------+
                                                   |
sources --> connector gateway --> evidence vault --> ingestion ledger
 ERP, banks, cards,          |                         |
 custodians, files, APIs     |                         v
                              +--> quarantine <--- parser / schema validator
                                                       |
                          reference data --------------+--> canonical transaction store
                                                               |
                                                       recon definition compiler
                                                               |
                                                    run orchestrator
                                                               |
                 +------------------ candidate & decision engine ------------------+
                 | blocking | exact rules | tolerances | allocations | N:M optimizer |
                 | conflicts | score/calibration | outcome/explanation               |
                 +------------------------------+------------------------------------+
                                                |               |
                                           matched groups     break/case service
                                                |               |
                                            balance controls   workflow, evidence,
                                                |               SLA, approvals, journals
                                                +-------+-------+
                                                        |
                                reporting / attestation / exports / audit evidence
```

**Control plane.** Stores tenants/legal entities, roles, segregation policies, reconciliation definitions, approved rule versions, calendars, materiality, notification routes, retention, and configuration change workflow. It must be versioned and independently auditable.

**Data plane.** Handles source evidence, parsing, canonicalization, matching, cases, and reporting. No data-plane worker may mutate approved policy directly.

**Evidence plane.** Append-only audit events and retained support objects. It should be queryable but protected from ordinary operational write/delete paths.

### 3.2 Deployment boundary

For a first production deployment, prefer a modular monolith with isolated workers and a relational transactional store over premature microservices. The correctness boundary is the reconciliation run and its auditable transaction. Split into services when independent scaling, hard tenant isolation, regulatory residency, or separate change-control domains require it.

Minimum production components:

- API/UI service with SSO, MFA, RBAC/ABAC, CSRF protection, rate limits, and secure session handling.
- Connector workers in a restricted network segment; outbound allow lists; per-connector credentials from a secret manager.
- Object store for encrypted immutable evidence and supporting documents.
- Relational database for canonical records, run snapshots, cases, workflow, and audit event metadata.
- Queue/orchestrator for idempotent ingestion and scheduled/backfill runs.
- Search/reporting replica that excludes secrets and uses field-level masking.
- Centralized security telemetry and a separate, immutable audit-log sink.

## 4. Canonical data model

### 4.1 Identity and lineage

Every record needs four identifiers; do not collapse them:

| Identifier | Purpose |
|---|---|
| `source_record_id` | Identifier emitted by the source, possibly non-unique across files. |
| `evidence_id` | Immutable received object and byte checksum. |
| `canonical_record_id` | Stable platform identity for the normalized item. |
| `record_version_id` | Immutable canonical representation produced by a specific parser/mapping version. |

Required lineage fields: `tenant_id`, `legal_entity_id`, `source_system`, `source_account_or_book`, `evidence_id`, `source_file_or_message_id`, `source_row_or_path`, `received_at_utc`, `effective_at_utc`, `business_date`, `parser_version`, `mapping_version`, `normalization_events`, `quality_status`, and `created_at_utc`.

### 4.2 Canonical transaction

```text
CanonicalTransaction
  identity: canonical_record_id, record_version_id, source_record_id
  scope: tenant, legal_entity, book/account, recon_population, business_date
  economics: signed_amount (decimal + ISO currency), quantity, price, tax, fee,
             FX rate, gross/net indicators
  lifecycle: event_type, status, trade_date, value_date, settlement_date,
             booking_timestamp, finality_status
  identifiers: references[], end_to_end_id, UETR, payment_id, invoice_id,
               trade_id, ISIN/CUSIP, counterparty, merchant, card/network IDs
  parties: account owner, counterparty, debtor/creditor, broker/custodian
  narrative: raw description, structured remittance, normalized tokens
  provenance: evidence pointer, source path, mapping version, field transforms
  controls: quality status, duplicate cluster, sensitivity classification
```

Use fixed-precision decimals and currency minor-unit validation; never use binary floating point for monetary equality. Preserve original amount/sign convention and record the canonical sign transformation explicitly.

### 4.3 Match group, not match pair

An industry-capable model is a **match group** with two or more allocations. A pair is only a special case.

```text
MatchGroup
  group_id, reconciliation_run_id, status, disposition
  rule_version_id, engine_version, confidence, auto_match_policy_id
  left_total, right_total, currency, residual_amount, residual_reason
  explanation_json, created_by, approved_by, timestamps

MatchAllocation
  group_id, canonical_record_id, side, allocated_amount, allocated_quantity,
  role (principal/fee/FX/tax/rounding), allocation_method, evidence
```

This supports 1:1, 1:N, N:1, N:M, partial allocation, net settlement, fees, FX, and reversal chains. Validate conservation: allocations cannot exceed the available record amount/quantity and group arithmetic must be exact under the stated rounding convention.

### 4.4 Cases, evidence, and workflow

```text
BreakCase: case_id, type, severity, materiality, linked_records[], root-cause,
           owner, SLA, status, ageing, resolution_code, resolution_evidence
WorkflowTask: task_id, action, assignee/queue, due_at, maker, checker, decision
EvidenceObject: hash, classification, retention, source, immutable URI, redaction state
AuditEvent: event_id, aggregate_type/id, sequence, actor/service, action,
            request/correlation ID, policy/version IDs, before_hash, after_hash, timestamp
```

Store a precise reason taxonomy separate from free text: missing-on-left/right, amount variance, date variance, duplicate, unexpected fee, FX variance, stale/in-transit, format/schema defect, source late/missing, rejected manual match, and control failure. Taxonomy supports reliable reporting and root-cause remediation.

## 5. Ingestion, normalization, and population controls

### 5.1 Connector contract

Each connector must implement:

1. Authenticate with short-lived, least-privilege credentials.
2. Fetch or receive with transport integrity/authenticity checks.
3. Create evidence object and content hash before parsing.
4. Assign idempotency key based on source identity plus content/version semantics.
5. Parse using a pinned schema/parser version.
6. Validate required fields and create canonical versions or quarantine records.
7. Emit per-file/message control totals and an ingestion audit event.

The system should accept CSV, ERP API exports, bank formats, SWIFT/ISO 20022, and custody feeds through adapters—not by spreading format-specific logic into the matching engine. ISO 20022 `camt.053` represents booked entries and balances; `camt.052` reports account activity; `camt.054` reports debit/credit notifications [S01, S02]. Keep message identifiers, entry references, booking/value dates, remittance fields, balances, and proprietary bank codes intact even when they are not currently used by a rule.

### 5.2 Data-quality gates

Before matching, record and enforce:

| Gate | Required result | On failure |
|---|---|---|
| Completeness | Expected file/message/calendar partition arrived. | Create control failure; do not auto-attest. |
| Integrity | Checksum/signature/transport status valid; no corruption. | Quarantine evidence. |
| Uniqueness | Duplicate delivery and duplicate business-record rules evaluated. | Deduplicate only through documented, reversible policy. |
| Schema | Required fields/types/version comply. | Quarantine invalid rows; flag run degraded. |
| Referential validity | Account, entity, currency, instrument, and reference data resolve. | Quarantine or create data-quality case. |
| Arithmetic | Debit/credit/net/balance and file control totals reconcile. | Block business matching for affected scope. |
| Timeliness | Source arrived within SLA and business cut-off. | Run with stale-data warning or escalate per policy. |

Normalisation functions—date timezone conversion, Unicode handling, casing, tokenization, leading-zero policy, sign direction, currency minor units—must be pure, versioned, tested, and recorded per field. Never silently "fix" a record in place.

### 5.3 Population-level proof

For every run persist: expected vs received source partitions, record count, debit/credit totals by currency, opening/closing balances where applicable, duplicate count, quarantined count, and records eligible for matching. This is the control that prevents a good match rate from masking a missing extract.

## 6. Matching engine architecture

### 6.1 Candidate generation is separate from decision

Use four layers:

1. **Blocking/indexing:** partition by tenant, legal entity, account/book, currency, sign, lifecycle, date window, amount bucket, reference keys, or instrument. It controls scale; it must never quietly remove a plausible candidate without a documented rule.
2. **Candidate features:** exact identifier/reference, amount residual, date distance, normalized name/narrative similarity, account/counterparty/instrument consistency, state compatibility, and aggregate arithmetic.
3. **Policy decision:** a deterministic rule declares auto-match, review suggestion, or reject. It emits the exact predicates and version.
4. **Global assignment/optimization:** resolve competition so the same available amount/quantity/record cannot be used twice. Produce unmatched residue explicitly.

Avoid a single opaque score deciding all outcomes. A numeric score can rank review candidates, but policy decides which score/rule band is safe to auto-match. Maintain confidence calibration by reconciliation definition and data population; a global "0.95 confidence" is not meaningful.

### 6.2 Rule ladder

Rules should be ordered from highest-evidence to lowest-evidence and versioned/approved independently:

| Band | Example | Auto-match condition |
|---|---|---|
| A: immutable identifier | Same UETR/end-to-end payment ID, account, currency, amount, valid lifecycle state. | Usually auto, unless duplicate/collision check fails. |
| B: exact economic match | Same signed amount/currency, date policy, reference or strong entity match. | Auto only with unambiguous candidate. |
| C: permitted operational variance | Known bank fee, FX/rounding, card discount, expected settlement lag. | Auto only under a named, approved variance model with bounds. |
| D: aggregate allocation | 1:N/N:1/N:M exact or permitted net arithmetic under constraints. | Auto only if unique and policy enables it; otherwise review. |
| E: fuzzy/suggested | Narrative/name similarity, heuristic relationship, learned rank. | Never auto until calibrated, approved, and monitored per population. |

The current ReconMatch tiers map to B (exact/windowed) and D (1:N/N:1 exact sum). To be industry-capable it requires N:M match groups, controlled tolerance/fee/FX models, explicit lifecycle constraints, global conflict resolution, and review-first fuzzy paths.

### 6.3 N:M and allocation algorithm

N:M matching is a constrained optimization problem, not nested pair matching:

```text
Inputs: eligible left records L, right records R, policy P
Generate bounded candidate groups through amount/date/reference blocks
For each group: prove arithmetic + constraints + explanation
Build conflict graph: allocation/record capacity conflicts are edges
Select maximum policy value subject to no-overallocation and group constraints
Emit selected MatchGroups and explicit unmatched residual
```

Required guardrails:

- Bound group size, date range, currency, entity/account, and search time; send oversized ambiguity to review rather than silently timing out.
- Keep principal, fee, tax, FX, and rounding components explicit; do not hide a non-zero residual.
- Check reversals/cancellations and status transitions before matching settled economics.
- Use integer minor units (after currency validation) for subset-sum arithmetic, then reconstruct decimals for display.
- Prefer an exact reference/amount group over lower-evidence similarity; record conflicts and rejected alternatives.
- Treat a manual allocation as a controlled event, not as a training label by default.

### 6.4 Tolerances and risk policy

Every tolerance must be a named policy with scope, owner, approval, effective dates, units, inclusive/exclusive bounds, rationale, and monitoring. For example:

```text
policy: CARD_NET_SETTLEMENT_FEE_V3
scope: merchant + processor + currency + legal entity
allow: gross settlement amount - approved processor fee records
date: settlement date +/- 2 business days
auto-match: only if fee line exists and residual is exactly zero after allocation
escalate: residual > 0, missing fee line, duplicate payout, aged > 2 days
```

Do not implement a universal percentage tolerance. It can mask material errors, scale incorrectly, and make audit review impossible. Materiality depends on account, legal entity, currency, product, and risk appetite.

### 6.5 Fuzzy and ML assistance

Fuzzy matching is useful when references are absent or data is obfuscated, but it is an evidence feature—not proof. For bank narratives, character n-grams, token overlap, transliteration, merchant/counterparty dictionaries, and controlled alias tables are often more useful than semantic embeddings. The BenchRec observation in this repository is consistent with this.

If using a learned model:

- Separate training labels from production decisions and preserve label provenance.
- Time-split validation; measure precision/recall and false-positive cost by domain, account, currency, and rule band.
- Set auto-match thresholds to a documented precision target, with ambiguity and out-of-distribution routing to review.
- Snapshot model/version/features and return a human-readable feature explanation.
- Monitor drift, override rate, break outcomes, calibration, and disparate effects where personal data are involved.
- Never let an LLM alter ledger data, approve an exception, or call external tools with unredacted source evidence without scoped authorization and audit.

## 7. Exceptions, workflow, attestation, and close

### 7.1 Case lifecycle

```text
NEW -> TRIAGED -> ASSIGNED -> INVESTIGATING -> PROPOSED_RESOLUTION
    -> INDEPENDENT_REVIEW -> RESOLVED | REJECTED | ESCALATED
    -> (re-open only by recorded event and policy)
```

Cases must link the exact records, candidate evidence, source objects, rules, prior decisions, communications, journal proposal, and resolution evidence. A case cannot be closed by a generic comment such as "resolved"; it needs a taxonomy code, evidence, actor, timestamp, and policy-compliant approval.

### 7.2 Segregation of duties

At minimum separate:

| Action | Cannot be sole approver of |
|---|---|
| Configure or activate a matching rule | That rule’s activation or its high-risk results |
| Ingest/replay a source feed | Data-quality attestation for that feed |
| Propose manual match/allocation | The same manual match/allocation |
| Prepare reconciliation | Review/attestation for the same high-risk scope |
| Propose journal | Journal approval/posting, where policy requires |
| Administer identity/roles | Their own privileged access grant |

Enforce these relationships in authorization queries, not only workflow-screen hints. Public close products similarly centre preparation, approval, review, support documentation, and role-based workflows [V02].

### 7.3 Attestation and close lock

A reconciliation period may be attested only when policy defines its population complete, material breaks are resolved or formally accepted, ageing exceptions are disclosed, required review occurred, and control failures are addressed or explicitly escalated. Attestation captures the prepared/reviewed assertions, versions, supporting evidence hash list, and scope. After close, lock operational results; corrections occur through an adjustment/reopen event that preserves the original attestation.

### 7.4 Journal integration

The platform should create **journal proposals**, not silently post accounting entries. A proposal includes debit/credit legs, accounting period, entity/account/dimensions, source case, policy, evidence, creator, reviewer, and ERP posting response. Use a transactional outbox/idempotency key for ERP delivery; reconcile the ERP posting acknowledgement back to the proposal. Commercial systems expose this controlled flow as an integration point [V02, V04].

## 8. Domain overlays

### 8.1 Cash / bank

- Inputs: prior-day/intraday bank report/statement, ERP cashbook, payment instructions/status, treasury system, bank master data.
- Controls: opening + activity = closing balance; booked vs pending state; duplicate statement detection; bank account ownership; value vs booking date; bank fees/interest; cut-off.
- Standards: model `camt.052`, `.053`, and `.054` without assuming all banks supply every optional field [S01–S03].
- Matching: payment IDs/reference first; exact signed amount/date and counterparty second; controlled bank fees and timing items; break escalation for unrecognized debits/credits.

### 8.2 Payments and cards

- Inputs: authorization, capture, reversal, clearing, scheme/processor settlement, merchant payout, fee, chargeback/refund, bank credit, GL, safeguarding account.
- Model lifecycle rather than a single transaction: one payment can have multiple authorization attempts, partial captures, split tenders, refunds, chargebacks, and net payouts.
- Control gross-to-net waterfall: authorized -> captured -> cleared -> settled -> payout -> bank -> GL; explain every fee, reserve, FX, and timing component.
- Cardholder data must be tokenized/masked and kept out of logs, exports, and broad analytics. PCI DSS scope includes systems that store/process/transmit cardholder data or can affect its security [S13].

### 8.3 Securities / post-trade

- Inputs: order/trade, allocation, confirmation, settlement instruction/status, custodian statement, CSD/CCP data, corporate actions, accounting and positions.
- Dimensions: instrument identifiers, quantity, price, trade/settlement date, account, safekeeping place, counterparty, currency, status, and settlement location.
- Perform both transaction and position/holding reconciliation; exceptions include failed/partial settlement, unmatched instruction, stale status, and corporate-action variance.
- Preserve status/finality: a matched instruction is not necessarily a settled trade. Swift describes dedicated reconciliation messaging for settlement reporting, pending instructions, movements, and holdings [S05].

### 8.4 GL / subledger and account substantiation

- Inputs: trial balance, GL detail, AP/AR/fixed-assets/payroll/inventory subledgers, bank/revenue evidence, prior-period reconciling items, journals, support documents.
- Process: prove account balance from support, roll forward opening balance + movements to ending balance, classify reconciling items, age them, and obtain preparer/reviewer sign-off.
- Controls: account risk rating, frequency, materiality threshold, mandatory templates, documented explanation of long-aged items, and close lock.
- Match rate is secondary; the output is a defensible account assertion. This is why commercial close systems pair matching with templates, workflow, support and account reconciliations [V02].

### 8.5 Intercompany

- Scope by legal entity pair, counterparty account, transaction type, currency, period, and agreement.
- Match bilateral transactions and balance confirmations; separate timing, FX, transfer pricing, and chart-of-account mapping differences.
- Automate elimination proposal only after bilateral agreement and policy checks; retain both entities’ evidence.
- Escalate disputed balances to a bilateral workflow with a clear owner on each side; do not let one entity unilaterally declare the relationship reconciled.

## 9. Security, privacy, and resilience

### 9.1 No "leak-proof" claim

No architecture can honestly guarantee that it will never leak or fail. The target is **defense in depth with explicit residual risk**, independently tested controls, rapid detection, incident response, and recoverability. NIST CSF 2.0’s Govern, Identify, Protect, Detect, Respond, and Recover functions supply a suitable operating model [S11].

### 9.2 Control baseline

| Threat / failure | Required controls |
|---|---|
| Unauthorized tenant/user access | SSO/OIDC, phishing-resistant MFA for privileged roles, tenant-scoped authorization in every query, least privilege, periodic access review, session/device controls. |
| Connector credential theft | Dedicated service identities, short-lived credentials, secret manager, rotation, network egress allow lists, no secrets in code/logs/evidence. |
| Sensitive-data exposure | Classification, field minimization, tokenization/masking, encryption in transit and at rest, per-tenant keys where required, export controls, DLP, retention/deletion workflow. |
| Record tampering | Append-only evidence/audit stream, object-lock/WORM retention where required, hash chaining/checkpoints, separate audit-write principal, signed release artifacts. |
| Malicious or accidental rule change | Versioned configuration, maker-checker activation, change ticket/evidence, test suite/shadow run, effective-date controls, rollback by new version. |
| Injection/unsafe uploads | Schema allow lists, content-type/size limits, malware scanning, CSV formula neutralization, parameterized queries, output encoding, isolated parsing workers. |
| Audit-log misuse | Structured events, redaction, restricted access, immutable sink, correlated timestamps, alerting on admin/security events. PCI logging intent is the ability to reconstruct who did what, where, when, and how [S14]. |
| Ransomware/availability loss | Immutable backups, restore tests, cross-zone replication, least-privilege backup deletion, RTO/RPO, reconciliation backlog replay design. |
| Supply-chain compromise | Dependency lockfiles/SBOM, signature/provenance verification, vulnerability management, CI secrets isolation, code review, SAST/DAST, infrastructure-as-code review. |

OWASP ASVS provides a testable application-security baseline [S16]. Treat logs as sensitive: OWASP notes application-level logs are needed beyond web-server logs [S17].

### 9.3 Audit-event minimum schema

Record: event ID, UTC timestamp with synchronized clock, tenant, actor/service identity, authenticated session/request/correlation ID, source IP/device context as appropriate, action, target resource, authorization decision, before/after version hashes, rule/config/engine version, outcome, reason code, and evidence links. Do **not** record passwords, tokens, full PAN, raw secrets, or unnecessary PII.

### 9.4 Privacy and residency

Classify fields before ingestion; use separate policies for personal data, payment data, trade data, and financial records. Implement regional placement and cross-border transfer controls when required. Retention must be configurable by entity, jurisdiction, data class, and legal hold; deletion must never violate required accounting/audit retention. GDPR’s data-minimisation, storage-limitation, integrity/confidentiality, and accuracy principles apply where relevant [S15].

## 10. Operating model, metrics, and assurance

### 10.1 Control ownership

| Role | Accountable for |
|---|---|
| Reconciliation owner | Definition, risk tier, materiality, SLA, sign-off policy, exceptions. |
| Data owner | Source availability, meaning, quality, lineage, change notice. |
| Operations preparer | Investigation and evidence-based resolution. |
| Independent reviewer/controller | Review, approval, escalation, control effectiveness. |
| Platform administrator | Access and configuration administration, not business approval. |
| Security/privacy | Threat model, security baseline, incident readiness, retention/privacy posture. |
| Internal audit / assurance | Independent design and operating-effectiveness testing. |

### 10.2 Metrics that cannot be gamed

- Population completeness rate; source timeliness and schema-drift rate.
- Auto-match **precision** (confirmed correct / auto-matched), recall/coverage, and false-positive monetary value—not just match rate.
- Manual override rate, override rejection rate, and rule-specific post-review error rate.
- Break count/value by root cause, severity, account, counterparty, and ageing bucket.
- SLA compliance; oldest open material exception; close-attestation timeliness.
- Reopened cases, post-close adjustments, and journal proposal/posting failures.
- Data-quality quarantine rate and time-to-repair.
- Rule/model drift and performance by population.

Run a labelled hold-out evaluation and a production post-review feedback loop. A high auto-match rate with poor precision is a financial-control defect. Basel expects accuracy, validation rules, exceptions reports, and escalation for poor data quality [S06].

### 10.3 Test strategy

| Layer | Required tests |
|---|---|
| Parsing / mapping | Golden raw files/messages, schema drift, missing/duplicate fields, value/date/sign/currency edge cases. |
| Data controls | Idempotency, control totals, balance roll-forward, quarantine, late/replayed file, source correction. |
| Matching | Exact, tolerance boundaries, competing candidates, allocation conservation, N:M ambiguity, reversal/status, deterministic rerun. |
| Workflow | SoD denial tests, review/escalation/reopen/attestation rules, evidence requirements. |
| Security | Authorization matrix/property tests, tenant isolation, secure upload, audit-log integrity/redaction, secret scanning, SAST/DAST, penetration test. |
| Resilience | Restore drills, replay from evidence, queue duplication/reordering, partial outage, cut-off/backlog processing. |
| Performance | Volume and worst-case candidate blocks, bounded N:M search, report/export load, API rate limits. |

## 11. Recommended build sequence for ReconMatch

### Phase 0 — establish the control foundation

1. Replace upload-only ephemeral flow with immutable source/evidence objects, canonical transaction versions, run snapshots, and audit events.
2. Add reconciliation definitions (scope, source mapping, policy, calendar, owner, SLA) and data-quality gates/control totals.
3. Make `MatchPair` evolve into `MatchGroup` + allocations with arithmetic conservation and no-double-use enforcement.

### Phase 1 — cash reconciliation MVP

1. Implement bank/ERP adapters and canonical cash model; support CSV first, then ISO 20022 `camt.053`/`.054` through a versioned adapter.
2. Add technical delivery status, statement/balance controls, idempotency, duplicate file detection, and replay.
3. Implement deterministic rules: identifiers, exact amount/date/reference, same-date low-text path, approved timing/fee policies, 1:N/N:1/N:M exact allocations.
4. Build break cases, manual-match proposal/review, evidence attachment, ageing, and simple attestation.

### Phase 2 — production controls

1. Add database persistence, tenant/legal-entity scope, SSO/MFA, RBAC/ABAC, SoD enforcement, and immutable audit sink.
2. Add rule lifecycle: draft -> test -> independent approval -> shadow run -> effective -> retired; never edit in place.
3. Add scheduled runs, operational dashboards, exports, controlled journal proposals, monitoring, backups, and restore/replay drills.

### Phase 3 — domain expansion

1. Payments/cards lifecycle and gross-to-net waterfall.
2. GL/subledger substantiation templates and close control.
3. Intercompany bilateral workflow and elimination proposal.
4. Securities trade/position/status reconciliation; this is a separate domain product, not just more fields on cash records.

### Phase 4 — intelligent assistance

Only after persistent ground truth and reviewer outcomes exist: rank review candidates, recommend rules, classify breaks, and draft explanations. Keep final financial actions deterministic and independently approved.

## 12. Gap analysis against the current ReconMatch repository

| Current strength | Industry implication / next change |
|---|---|
| Decimal amounts, deterministic engine, rule-produced confidence | Retain this core. Add run/rule/data version IDs and an explicit explanation trace. |
| Exact and windowed 1:1, 1:N, N:1 matching | Generalize to MatchGroup allocations and bounded N:M candidate optimization. |
| Break classification hints | Turn each break into a persistent case with taxonomy, owner, SLA, evidence, review, and resolution state. |
| Greedy single-pass assignment | Retain as a baseline only where policy proves ordering is safe; add conflict graph/optimization for aggregate groups and store rejected candidates. |
| CSV upload and synthetic evaluation | Add immutable evidence, idempotent ingestion, data-quality control totals, source adapters, production-labelled evaluation, and replay. |
| Stateless demo, no auth or persistence | Suitable for demo only. Production requires tenancy, identity, authorization, configuration change control, audit trail, backup/recovery, and privacy controls. |
| BenchRec finding: text gate and same-date hole | Add review-first, low-text candidate path using amount/date/blocking plus character-level attributes; validate precision independently. |

## 13. Architecture acceptance checklist

A release is not industry-ready unless all applicable statements are demonstrably true:

- [ ] Every result can be reproduced from immutable source evidence and versioned configuration.
- [ ] Every input population has completeness, duplication, quality, and control-total evidence.
- [ ] Every auto-match has a policy version, explanation, and precision monitoring.
- [ ] N:M allocation conservation and conflict/no-double-use constraints are tested.
- [ ] Manual matches, rule changes, exclusions, journals, and approvals are append-only, attributed, evidenced, and subject to SoD.
- [ ] A reconciliation cannot be attested while required data/control failures or material exceptions remain unresolved without recorded formal acceptance.
- [ ] Tenant and legal-entity authorization is enforced server-side for every operation and export.
- [ ] Sensitive data is minimized, masked, encrypted, retained/deleted under policy, and absent from ordinary logs.
- [ ] Security events and business audit events are tamper-evident, redacted, monitored, and retained per policy.
- [ ] Backups, evidence replay, late-file recovery, and incident response have been tested—not merely designed.
- [ ] Domain owners, controllers, security/privacy, and internal audit have approved the relevant control design.

## 14. What this study does not claim

This is an architecture study, not legal advice, an audit opinion, a PCI/SOC/ISO certification, or a representation that any implementation is "leak-proof." Regulatory obligations, accounting policy, retention, residency, materiality, risk tolerance, and required assurance vary by jurisdiction, institution, product, and customer contract. Confirm them with qualified legal, compliance, security, privacy, finance-control, and audit stakeholders before design freeze.
