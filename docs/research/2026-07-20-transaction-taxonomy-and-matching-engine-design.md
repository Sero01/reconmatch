# Transaction Taxonomy and Matching Engine Design

> A companion to the [industry-standard reconciliation architecture study](2026-07-19-industry-standard-reconciliation-architecture.md). This document explains what major transaction populations a serious reconciliation platform must represent, how they are matched, and how matching remains safe and fast at high volume. Source IDs refer to the [companion source register](2026-07-20-transaction-taxonomy-and-matching-engine-design-sources.md).

## Executive summary

Reconciliation engines fail when they treat every record as `date + description + amount`. Financial events have lifecycle, direction, finality, component, account, legal-entity, and instrument semantics. A payment authorization, a card payout, a bank statement entry, a securities settlement instruction, and a month-end GL balance can all contain an amount but require different matching constraints.

At scale, the winning architecture is not an all-pairs fuzzy comparison. It is:

```text
prove population -> normalize -> partition -> block/index -> exact high-evidence matches
                -> bounded candidate graph -> optimize connected components
                -> manual-review ambiguity -> retain every decision/exclusion
```

The central rule is: **reduce the candidate graph only with constraints that cannot discard a valid match under the current policy; use expensive comparison and optimization only inside the resulting small components.** Blocking is a standard record-linkage response to the impracticality of full cross-products [A05].

## 1. A universal transaction model

### 1.1 Every financial event has more than an amount

The platform canonical model must represent the following dimensions even if a first cash connector populates only a subset:

| Dimension | Examples | Why a matcher needs it |
|---|---|---|
| Scope | tenant, legal entity, branch, book, account, portfolio, merchant | Prevent cross-entity/account matches. |
| Economics | currency, signed gross/net amount, quantity, price, tax, fee, FX | Proves conservation and explains differences. |
| Timing | event/trade, authorization, booking, value, settlement, posting dates | A date difference can be expected or a break depending on lifecycle. |
| Identity | source ID, end-to-end ID, UETR, invoice, trade, order, card/network, instrument identifiers | Highest-evidence matching keys. |
| Parties | debtor/creditor, merchant, counterparty, broker, custodian, employee | Controls allowed counterparties and supports linkage. |
| State/finality | pending, booked, accepted, rejected, cleared, settled, reversed, returned, cancelled | Prevents matching an initiation as if it were final settlement. |
| Components | principal, fee, tax, discount, reserve, interest, FX, rounding | Supports gross-to-net and allocation matching. |
| Provenance | source object, row/message path, parser/mapping version, received time | Makes every result reproducible and auditable. |

ISO 20022’s business model deliberately defines common concepts across payments, securities, trade services, FX, cards, and related services [T02]. Use this as a semantics guide, not as a reason to expose every ISO field in every product screen.

### 1.2 Transaction, position, balance, and control population

| Object | What is compared | Matching consequence |
|---|---|---|
| Transaction | A discrete economic event | Usually reference/amount/date/lifecycle rules. |
| Lifecycle event | State change of a transaction | Chain to the same business identity; do not independently duplicate-match it. |
| Position / holding | Quantity/value at a point in time | Reconcile lots, settled/unsettled quantities, price/FX valuation, and corporate actions. |
| Balance | Aggregate account total | Prove roll-forward and substantiate open reconciling items; line matching alone is insufficient. |
| Control population | Expected data delivery or report | Prove completeness, uniqueness, timeliness, and totals before business matching. |

## 2. Major transaction families to support

### 2.1 Cash and bank-account activity

**Population.** Bank statement/account-report entries, ERP cashbook entries, payment instructions and statuses, treasury cash positions, bank fees/interest, direct debits, standing orders, cheques, lockbox, and cash deposits/withdrawals.

**Lifecycle.** Initiated -> accepted/rejected -> pending -> booked/value dated -> returned/reversed/corrected. Booking date and value date are not interchangeable. A bank statement normally reports booked entries and balances; intraday reports/notifications can be pending or earlier in the lifecycle [T01].

**Matching patterns.**

- 1:1 payment reference or end-to-end ID.
- 1:1 exact signed amount, account, currency, date/window, and counterparty.
- 1:N customer remittance against invoices; N:1 bulk payment/batch settlement against ledger lines.
- N:M cash pool/netting transfer under explicit allocation policy.
- Balance roll-forward: opening balance + debits/credits = closing balance.
- Timing item: initiated ledger payment waiting for bank booking.

**Frequent breaks.** Missing bank entry, unposted cashbook item, duplicate file, wrong value date, bank fee, bank interest, returned debit, stale pending payment, and balance/control-total mismatch.

### 2.2 Account-to-account and payment-rail transfers

**Population.** Domestic wires, RTGS, ACH/direct debit, instant payments, cross-border transfers, SWIFT messages, payment batches, returns, recalls, investigations, and correspondent-bank charges.

**Important semantics.** Separate payment instruction, clearing, interbank settlement, beneficiary credit, and bank-account booking. ISO distinguishes payment initiation (`pain`), payment clearing and settlement (`pacs`), cash reporting (`camt`), and remittance advice (`remt`) [T01]. A status is evidence about a lifecycle stage, not interchangeable evidence of settlement.

**Matching patterns.**

- Instruction-to-status and instruction-to-bank-entry by immutable identifiers first.
- Batch header/control-total to member records, then member records to settlement.
- Gross principal plus separately booked correspondent fees.
- FX payment: instructed amount/currency versus interbank settlement amount/currency plus approved FX rate and fee components.
- Return/reversal linked to original payment—not treated as a second unrelated debit/credit. ACH rules, for example, constrain reversal reason, timing, and fields that remain identical to the original entry [T06].

### 2.3 Card acquiring, issuing, and wallet payments

**Population.** Authorization, authorization adjustment, capture, presentment/clearing, settlement, merchant payout, interchange/processor fee, reserve/holdback, refund, reversal, chargeback, representment, dispute, and network fee. Wallets add funding, transfer, withdrawal, promotional credit, and ledger movements.

**Lifecycle.** One consumer purchase can create many records and partial states. An authorization may expire; captures can be partial/multiple; settlement can net fees, refunds, reserves, and chargebacks; a payout can aggregate thousands of payments.

**Matching patterns.**

- Lifecycle-chain matching by network/acquirer/merchant transaction ID.
- 1:N authorization to partial captures; N:1 cleared items to payout.
- Gross-to-net waterfall: cleared sales − refunds − chargebacks − fees − reserves = settlement/payout.
- Payment processor payout to bank statement and then GL.
- Chargeback/dispute linked to original payment and accounting adjustment.

**Non-negotiable design point.** Do not store raw PAN or sensitive authentication data in ordinary reconciliation records, search indexes, logs, exports, or attachments. Data scope must be minimized and isolated; PCI DSS applies to systems that store, process, transmit, or can affect cardholder-data security (see prior architecture study, source S13).

### 2.4 Merchant commerce, receivables, payables, and billing

**Population.** Sales order, shipment/delivery, invoice, credit memo, cash receipt, payment application, purchase order, goods receipt, supplier invoice, payment, rebate, discount, tax, and write-off.

**Matching patterns.**

- Invoice-to-receipt (1:1, partial, or many invoices paid by one remittance).
- Purchase-order -> goods receipt -> vendor invoice (three-way matching; this is validation plus reconciliation).
- Credit memo/refund against original invoice/payment.
- Remittance/advice allocation across invoices, with discount/tax/withholding components.
- Aged open-item reconciliation and AR/AP balance-to-subledger roll-forward.

**Frequent breaks.** Short pay, overpay, unidentified receipt, duplicate invoice, price/quantity/tax variance, unallocated credit, duplicate payment, and unrecorded supplier fee.

### 2.5 Payroll, expense, and benefits

**Population.** Gross wages, tax withholding, employer contributions, benefit deductions, reimbursement, payroll funding, payroll provider debit, employee payment batch, statutory remittance, and GL journals.

**Matching patterns.**

- Payroll register gross-to-net decomposition.
- Payroll funding account debit to employee-payment and tax-payment batches.
- Employee expense claim to card/receipt/reimbursement, under policy.
- Payroll provider invoice to service fee and cash debit.

**Control distinction.** Personally identifiable employee information belongs in protected reference/evidence systems. Match on surrogate/employee ID and minimized fields where possible; operations users should not need unrestricted payroll records to resolve a bank batch.

### 2.6 Loans, deposits, and treasury

**Population.** Loan drawdown, repayment, principal, accrued/paid interest, fees, amortization, deposit, withdrawal, rollover, collateral, margin, cash-pool sweep, money-market placement, and bank confirmations.

**Matching patterns.**

- Contract/lender/deal ID plus cash flow schedule.
- Principal/interest/fee component allocation.
- Accrual-to-payment and amortization roll-forward.
- Treasury position/balance confirmation to internal deal system and GL.
- Cash-pool sweep multi-entity allocation with legal-entity and intercompany constraints.

### 2.7 Foreign exchange and derivatives

**Population.** FX spot/forward/swap, option premium/exercise, NDF fixing/settlement, interest-rate swap cash flows, futures variation margin, collateral/margin calls, novation, compression, and trade-repository reports.

**Matching patterns.**

- Trade economics: trade ID, instrument, buy/sell currencies, notional, rate, value date, counterparty.
- Confirmation/affirmation to front-office trade.
- Settlement leg(s) to bank/correspondent activity; two legs must not be collapsed into one amount comparison.
- Margin/collateral call to custody/CCP cash and securities movements.
- Valuation/position and P&L to risk/accounting populations.

**Frequent breaks.** Rate/date/counterparty disagreement, missing confirmation, partial settlement, collateral dispute, duplicate amended trade, and mismatch between trade status and settlement status.

### 2.8 Securities, custody, and post-trade operations

**Population.** Orders, executions, allocations, confirmations, settlement instructions/status, custody movements, holdings, pending/fails, securities lending/borrowing, repos, collateral, corporate actions, income, and fees.

Securities require trade, position, and settlement reconciliation. ISO 15022 includes allocation, trade confirmation, settlement instruction/confirmation, holdings, transaction statements, pending transactions, lending, and collateral messages [T04]. Swift’s reconciliation scope includes movements, holdings, pending instructions, and counterparties/intermediaries across the post-trade chain [T05].

**Matching patterns.**

- Trade-date economics (instrument, quantity, price, side, account, counterparty) to confirmation.
- Settlement instruction to custodian/CSD status and final movement.
- Position/holding reconciliation by instrument, location, available/settled/pledged quantity, and valuation.
- Corporate-action entitlement/calculation/payment to custody and accounting records.
- Fail/partial settlement ageing, buy-in, and claim workflow.

### 2.9 General ledger, subledger, close, and journals

**Population.** Trial balance, GL journals, AP/AR/fixed assets/inventory/payroll subledgers, accruals, prepayments, depreciation/amortization, intercompany balances, consolidation adjustments, and supporting schedules.

**Matching patterns.**

- Journal-to-subledger/detail support.
- Account roll-forward: opening + debits − credits + adjustments = closing.
- Balance substantiation to independent support/custodian/bank/aging.
- Recurring accrual/reversal pair.
- Journal proposal to ERP posting acknowledgement.

The unit of completion is an account assertion with support and reconciling-item ageing—not merely a set of line matches.

### 2.10 Intercompany and consolidation

**Population.** Cross-charge invoice, intercompany loan, cost allocation, transfer-pricing adjustment, cash-pool movement, dividend, elimination, FX translation, and counterparty confirmation.

**Matching patterns.**

- Entity A receivable/revenue to entity B payable/expense, mapping account and currency differences.
- Many-to-many cost allocation with a controlled allocation driver and bilateral evidence.
- Intercompany loan principal/interest and cash movements.
- Consolidation elimination proposals after bilateral confirmation.

**Control.** Each party owns its books. A unilateral record is evidence of a claim, not proof that the relationship is reconciled.

### 2.11 Tax, regulatory, and operational data integrity

**Population.** Sales/VAT/GST tax, withholding, tax payments/refunds, regulatory transaction reports, safeguarding calculations, capital/liquidity reports, KYC/AML operational feeds, and fee/revenue reports.

**Matching patterns.**

- Tax engine output to invoice/GL/payment/remittance.
- Regulatory report record to source transaction and submitted/acknowledged status.
- Safeguarding population to segregated-bank balances, customer liabilities, and permitted adjustments.
- Source-to-report field-level integrity reconciliation.

This family often needs **comparison plus completeness/validity controls**, even when there is no natural opposite-side transaction.

## 3. Matching taxonomy

### 3.1 Match relationship cardinality

| Type | Definition | Example | Main risk |
|---|---|---|---|
| 1:1 | One record economically equals one other record. | Invoice payment. | Duplicate candidates. |
| 1:N | One record allocates to many. | One bank receipt pays several invoices. | Over-allocation / residual. |
| N:1 | Many records aggregate to one. | Payroll lines settle as one bank debit. | Combinatorial explosion. |
| N:M | Multiple records on each side form a constrained economic group. | Card transactions/refunds/fees net into payouts. | Ambiguous group selection. |
| 0:1 / 1:0 | Expected unmatched item. | Bank fee absent from ledger. | Mistakenly forcing a match. |
| Chain | Several lifecycle states of one business object. | Authorization -> capture -> settlement -> payout. | Double-counting lifecycle events. |
| Position/balance | Aggregates/holdings compared at a point in time. | Custodian vs internal position. | Offsetting line errors hide in total. |

### 3.2 Evidence type

| Match type | Evidence | Correct use |
|---|---|---|
| Immutable-key exact | Same globally/locally unique ID with valid scope/state. | Highest confidence; still check duplicates/reuse. |
| Composite-key exact | Deterministic tuple: account, currency, signed amount, date, reference, party. | Standard cash and ledger baseline. |
| Temporal | Date/time window, business calendar, expected cut-off. | Only with lifecycle-aware window. |
| Amount tolerance | Difference within named permitted variance. | Fees, FX, rounding, discounts—not a universal safety valve. |
| Reference transformation | Normalised/truncated/structured remittance/alias mapping. | Versioned, explainable transformations. |
| Fuzzy similarity | Token, character n-gram, edit distance, phonetic/entity alias. | Candidate ranking or review-first; calibrated auto-match only after evidence. |
| Aggregate arithmetic | Sum/quantity/net position equals under allocation constraints. | Batches, split payments, net settlements. |
| State / lifecycle | Legal transition/original relationship. | Returns, reversals, cancellations, amended trades. |
| Balance / roll-forward | Opening + movement = closing and support equality. | Cash, GL, positions. |
| Rule/policy | Explicit business rule (fee schedule, settlement delay, mapping). | Approved and versioned; monitor exceptions. |

### 3.3 Match disposition

Do not reduce a matcher’s output to Boolean. It must emit:

```text
AUTO_MATCHED          policy permits and evidence is unique
SUGGESTED_FOR_REVIEW  plausible candidate, insufficient auto-match evidence
IN_TRANSIT            valid expected timing state, owner and ageing applied
UNMATCHED             no candidate under policy
DATA_QUALITY_HOLD     record/population cannot be safely matched
CONFLICT              candidates compete or allocations exceed capacity
EXCLUDED              versioned policy exclusion, with reason/evidence
```

### 3.4 Matching is not deduplication

Deduplication asks whether two source records are accidental duplicates. Reconciliation asks whether records from different representations describe the same economics. Run duplicate detection before and after candidate generation; a duplicate input can create a false exact match and mask a genuine break.

## 4. The high-volume matching pipeline

### 4.1 Complexity: why all-pairs comparison fails

If `n` left and `m` right records are compared blindly, candidate count is `n*m`. At 1 million records per side that is `10^12` comparisons before any allocation search. Even fast string scoring cannot make that safe or cheap.

The engine must first prove the population, then successively reduce work:

```text
1. ingestion/idempotency + quality gates
2. hard scope partition
3. high-recall blocks
4. cheap exact predicates
5. candidate feature/scoring
6. connected-component split
7. exact or bounded optimizer per component
8. persist outcome, residual and rejected alternatives
```

### 4.2 Hard partitions: constraints, not guesses

Partition by values that a valid match cannot cross under the definition: tenant, legal entity, reconciliation definition, side, account/book, currency, sign where policy requires it, instrument, settlement location, and business period. Partitioning creates independent work shards and reduces memory/lock contention.

Never partition on a field that can legitimately differ (for example, booking date vs value date) unless the rule explicitly declares it invariant. Keep a documented exception route for incomplete or cross-scope data.

### 4.3 Blocking and indexing

Blocking produces a high-recall candidate superset. It must be measured with:

- **blocking recall:** fraction of known true links that occur in at least one block;
- **reduction ratio:** fraction of all-pairs comparisons eliminated;
- **block-size distribution:** mean hides pathological hot blocks;
- **candidate budget violations:** records/blocks that exceed configured limits.

Standard block keys for financial matching:

| Block family | Example | Best for | Failure mode |
|---|---|---|---|
| Exact hash | `(entity, account, currency, signed_minor_amount)` | Exact amount matches | Popular rounded amounts create huge blocks. |
| Sort/range | `(account, currency, date)` sorted by amount | Amount/date tolerances | Large date window becomes dense. |
| Reference inverted index | normalized reference/token -> IDs | Payments/invoices/trades | Missing/dirty references. |
| Composite hierarchy | exact ID, then ref+amount, then amount+date | Progressive evidence | Earlier low-quality rule must not consume records. |
| N-gram/prefix index | selected description/party tokens | Fuzzy review candidates | High-frequency tokens produce fan-out. |
| Lifecycle index | original ID / status / merchant transaction ID | Returns/cancellations | Incorrectly treating amendment as a new transaction. |

Blocking is a recognized way to avoid impractical full comparison in record linkage [A05]. Use multiple independent block keys (logical union), not one brittle key, then deduplicate candidates by record pair/group ID. Capture the block reason for audit and evaluation.

### 4.4 Data structures and database execution

- Store monetary values as integer minor units for index/range and subset arithmetic, alongside validated decimal/currency representation.
- Maintain composite B-tree/range indexes for ordered date/amount lookups and hash/inverted indexes for exact references.
- Use sort-merge for large, ordered equality/range-compatible streams; use hash join for equality blocks that fit memory; spill deterministically to partitioned external execution when they do not.
- Carry record IDs and compact feature columns during candidate generation; fetch bulky narrative/evidence only for survivors (late materialization).
- Write candidates in batches/partitions; never materialize the global cross product.
- Persist run snapshots and component boundaries so retries replay deterministically.

Join strategy is an engineering choice shaped by memory, I/O, and distributed architecture, not an implementation detail; external-memory and distributed join theory makes this explicit [A08]. Parallel partitioned sort-merge work demonstrates high scale on large main-memory systems but must handle skew [A07].

### 4.5 Candidate scoring: cheap before expensive

Evaluate features in an order that maximizes rejection per unit cost:

1. Scope, lifecycle, currency, sign, and hard identifier compatibility.
2. Exact amount or approved residual bound.
3. Date/window and business-calendar rule.
4. Structured references and counterparty/instrument checks.
5. Cheap token/character overlap.
6. Expensive edit-distance, model inference, or subset/flow optimization only for survivors.

Represent each candidate with immutable feature values and a rule/score explanation. Use a score only to rank candidates or express a calibrated decision policy. Record-linkage theory provides a principled evidence/error-cost framing [A06], but raw similarity is not a financial authorization.

### 4.6 Connected components: the practical optimization boundary

Create a bipartite graph: left/right records are nodes, candidate links are edges. Split it into connected components. Components with no shared nodes can be decided independently and in parallel.

```text
L1 -- R1      L3 -- R4 -- L4
 |             |
R2             R5

component A    component B
```

This protects global correctness without solving one giant global problem. Persist a `component_id`, edge count, amount range, and algorithm selected. A component that exceeds time/size/candidate limits becomes an explicit review/exception outcome, not a silent degraded match.

### 4.7 Priority order for high-volume execution

1. Exact immutable-ID and exact composite 1:1 candidates with uniqueness checks.
2. Exact aggregate groups that can be proven without ambiguity.
3. Small components solved with exact assignment/allocation algorithms.
4. Larger components under strict policy/budget; return suggestion or review if proof cannot complete.
5. Keep all unmatched residual; re-run only affected components after human decision or new data.

Do not greedily consume a record because it has a high local score when a slightly weaker edge unlocks a stronger globally consistent group. Greedy matching is acceptable only where a rule proves its ordering is safe.

## 5. Optimization methods by matching shape

### 5.1 Exact one-to-one: joins, then assignment

For an unambiguous exact key, a database join plus uniqueness rule is enough. For multiple plausible 1:1 candidate edges, formulate a weighted bipartite assignment:

```text
maximize sum(score[left,right] * selected[left,right])
subject to each left record selected at most once
           each right record selected at most once
           selected is binary
```

The Hungarian method solves the classical linear assignment problem [A01]. Shortest augmenting-path variants are practical for dense and sparse assignment [A02]. Use it only *inside a bounded component*; a million-by-million dense matrix is not a viable input.

**Use when:** one record on each side, every candidate has a meaningful comparable cost/score, and no record can be reused.

**Do not use when:** allocations, fees, partial amounts, or many-to-many groups are required; forcing those into 1:1 creates false matches.

### 5.2 Exact one-to-many / many-to-one: constrained subset sum

For an aggregate amount target, search subsets of eligible records whose amounts equal the target under date/scope/cardinality rules. Subset sum is NP-complete in the general case; meet-in-the-middle reduces the naive `2^n` search to roughly `2^(n/2)` but remains exponential [A03].

**Production guardrails:**

- Block tightly by entity/account/currency/sign and narrow date window.
- Cap component size, subset cardinality, candidate count, and wall time.
- Prefer reference/shared batch ID before arithmetic-only matching.
- Use integer minor units and exact conservation.
- Require unique solution or route ambiguity to review.
- Record exhausted-search/timeout as a visible outcome.

For small bounds (for example 2–5 items), enumeration with pruning is often faster and easier to explain than a general solver. For larger bounded groups, use meet-in-the-middle, dynamic programming when amount range is small, or a solver under strict time budget.

### 5.3 Many-to-many: min-cost flow or integer programming

N:M netting/allocation needs capacity on records and conservation by component. A flow model can express supply/demand and edge costs:

```text
source -> left record (capacity = available amount/quantity)
left -> right candidate (cost = evidence penalty; capacity = permitted allocation)
right -> sink (demand/capacity = available amount/quantity)
```

Min-cost flow selects allocations that satisfy capacities while minimizing penalty. Assignment is a special case of network optimization; standard flow texts cover shortest path, assignment, and min-cost flow formulations [A04].

Use a flow model only when partial allocation semantics are legitimate. If a record must match whole, add binary/group constraints; that can become integer programming. Keep financial components (principal/fee/FX/tax) as separate nodes or constraints so the optimizer cannot invent an unexplained residual.

**Use when:** card payouts, net settlements, collateral, cash pooling, or invoice allocations permit controlled split allocation.

**Reject/review when:** constraints allow too many equivalent solutions, policy cannot explain allocations, or the component exceeds approved solver budget.

### 5.4 Position and balance: roll-forward and constrained comparison

Position reconciliation does not usually need a pairwise optimizer. Aggregate canonical records by agreed dimensions—entity, account, instrument, safekeeping location, settled/pending status, date—and compare quantity/value/cost. Then drill to transactions only for non-zero differences.

Balance reconciliation proves a roll-forward and explains all reconciling items:

```text
opening + recognized movements + approved adjustments = closing
```

Prevent cancellation by separately tracking debit/credit or buy/sell counts and values, quantity, and status buckets.

### 5.5 Fuzzy and probabilistic matching: ranking, not magic

Use normalized character n-grams, token overlap, aliases, edit distance, and structured field agreements to rank candidates. Establish thresholds from labelled, time-separated data and report precision/recall/calibration by transaction family. Then apply one-to-one/global capacity constraints after scoring.

Fuzzy links should ordinarily be `SUGGESTED_FOR_REVIEW`. Auto-match requires a validated population-specific rule, a unique candidate margin, a maximum financial-risk threshold, and monitored false-positive outcomes. Never use semantic similarity alone to authorize a cash, trade, or GL match.

## 6. Skew, ambiguity, and performance safety

### 6.1 Skew is the hidden scale killer

Common amounts (`0`, `100.00`), batch dates, popular merchants, blank references, and omnibus accounts create massive blocks. Average candidate count is misleading; monitor p95/p99/max component size and time.

Mitigations:

- Refine hot blocks with an additional invariant (account, reference prefix, party, time-of-day, status).
- Process high-frequency keys by dedicated partition/queue; never let one key stall the run.
- Cap generic/blank-description fuzzy candidates per record.
- Detect and report low-information records; do not manufacture a match from them.
- Use deterministic tie-breaking only after policy; a deterministic arbitrary match remains arbitrary.

Parallel database research specifically identifies skew as a threat to near-linear speedup [A07].

### 6.2 Candidate and solver budgets

Budgets are safety controls, not merely performance knobs:

| Budget | Example policy | If exceeded |
|---|---|---|
| Candidate edges per record | 200 review candidates | Retain best explainable candidates; create ambiguity case. |
| Component records/edges | 500 records / 10,000 edges | Split only with valid invariant; otherwise review queue. |
| Aggregate cardinality | at most 5 records per side for auto-match | Require review or batch identifier for larger groups. |
| Optimization time | 500 ms per component auto-match | Cancel safely; persist timeout and route to review. |
| Fuzzy comparison work | bounded per partition/run | Defer/requeue, never silently lower threshold. |

Choose actual values empirically per reconciliation definition. Persist the budget/version and reason when an item is not auto-matched.

### 6.3 Incremental and streaming reconciliation

For intraday scale:

1. Append evidence and canonical versions idempotently.
2. Assign deterministic partition/block keys.
3. Recompute only affected open components plus their candidates.
4. Keep a watermark/cut-off and late-event policy.
5. Do not alter a closed/attested match; create correction/reopen events.

Maintain availability state: an already allocated record cannot be reused until a controlled unmatch/reversal releases its capacity. Exactly-once processing is not guaranteed by queues alone; enforce idempotency in the data model using source/evidence keys and transactional writes.

### 6.4 Parallelism model

Parallelize only independent partitions/components. Within each worker:

- use deterministic ordering and stable candidate IDs;
- pin rule, reference-data, and engine versions for the run;
- avoid shared mutable counters as decision inputs;
- write through transactional outbox/event log;
- retry idempotently.

This produces same-input/same-version reproducibility regardless of worker scheduling, a necessary property for audit and incident replay.

## 7. Engine selection matrix

| Transaction / problem | Preferred first method | Escalate to | Never do |
|---|---|---|---|
| Bank cash 1:1 | Exact ID/composite hash/range join | Small 1:1 assignment or review ranking | Global fuzzy all-pairs comparison. |
| Invoice receipt allocation | Remittance/reference + bounded allocation | Small subset/flow or reviewer allocation | Treat every receipt as one invoice. |
| Payroll batch | Batch ID/control total + N:1 exact sum | Bounded subset by payroll run | Match individual employee names to bank narrative. |
| Card payout | Processor IDs + gross-to-net component waterfall | N:M flow with explicit components | Net amount alone as proof. |
| ACH return/reversal | Original relation + status/reason/time window | Investigation workflow | Match as unrelated opposite-signed payment. |
| Securities trade | Trade/instrument/economics/state keys | Sparse 1:1 assignment/review | Match only amount/date. |
| Securities position | Aggregate dimensional comparison | Transaction drill-down | Offset quantities across instrument/location/status. |
| GL account | Roll-forward + support mapping | Break/case workflow | Declare balance reconciled because net is zero. |
| Intercompany | Entity pair + agreement/mapping + bilateral workflow | N:M allocation/FX policy | One party self-certifies match. |
| Fuzzy bank/ERP text | Candidate ranking after financial blocks | Human review / calibrated policy | Let text similarity override conflicting economics. |

## 8. Implementation implications for ReconMatch

### 8.1 Preserve and extend the current strengths

ReconMatch already has Decimal arithmetic, deterministic tier ordering, exact 1:N/N:1 matching, a no-double-use intent, confidence, and break classification. Retain them. The new requirements are structural:

1. `MatchPair` becomes `MatchGroup` plus component-level allocations and residuals.
2. Every run gets frozen input, configuration, reference, engine, and candidate-graph versions.
3. Candidate generation becomes a distinct module with partition/block metrics, not hidden inside tier loops.
4. Global resolution works per connected component; the current global greedy order becomes a policy choice, not the only algorithm.
5. The engine returns explicit `CONFLICT`, `AMBIGUOUS`, `IN_TRANSIT`, and `DATA_QUALITY_HOLD` outcomes.

### 8.2 Immediate matching additions

- **Same-date, low-text 1:1 path:** amount/date/account/currency block plus character-level attribute features, review-first threshold, and one-to-one conflict resolution. This addresses the BenchRec gap without weakening high-precision rules.
- **N:M exact-group path:** bounded candidate graph, cardinality/time limits, exact arithmetic, and unique-solution requirement.
- **Tolerance policies:** replace a generic tolerance with named fee/rounding/FX/timing models that expose residual components.
- **Lifecycle links:** original/reversal/return/duplicate semantics before amount matching.
- **Population controls:** control totals, duplicate-source detection, and unmatched counts before headline matching metrics.

### 8.3 Evaluation additions

Track per rule and per transaction family:

- candidate blocking recall and candidate volume;
- auto-match precision, recall/coverage, ambiguity, and monetary false-positive impact;
- runtime and memory by partition, block, and component p50/p95/p99;
- optimization timeout/budget outcomes;
- duplicate and source-quality holds;
- reviewer accept/reject/override outcomes;
- residual/ageing by break reason.

Do not tune on a single aggregate F1 score. A safe matching engine optimizes coverage **subject to** a strict false-positive constraint and an auditable operational budget.

## 9. Acceptance tests for a scalable matching engine

- [ ] Adding a duplicate source file does not create duplicate canonical records or matches.
- [ ] A control-total/balance failure prevents auto-attestation and is visible separately from business breaks.
- [ ] A true link in a labelled sample survives at least one configured block; blocking recall is measured.
- [ ] Candidate count is bounded; hot blocks create an explicit ambiguity/performance event.
- [ ] Exact 1:1 conflict graph chooses the globally best valid assignment, not merely first/highest local edge.
- [ ] N:1/1:N/N:M allocations conserve every amount/quantity and leave explicit residuals.
- [ ] An aggregate search timeout never produces a partial auto-match.
- [ ] Return/reversal/cancellation attaches to its original lifecycle chain.
- [ ] A re-run with the same frozen data/rules/engine produces identical outcomes and explanations.
- [ ] Parallel workers and retries cannot allocate a record twice.
- [ ] Fuzzy recommendations can be reviewed with the underlying features and do not silently bypass policy.

## 10. Boundaries and cautions

This study describes general-purpose design, not an instruction to enable every transaction type in one release. Each domain needs its own data contract, lifecycle states, policy owner, reference data, quality gates, labelled evaluation, and operational workflow. Algorithmic optimality is not the same as financial correctness: an optimizer can perfectly solve the wrong constraint model.

Start with cash, then choose the next vertical based on available source data and review labels. Build the candidate-generation, grouping, evidence, and control foundations once; add domain-specific semantics deliberately.
