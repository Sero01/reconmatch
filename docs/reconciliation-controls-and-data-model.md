# Reconciliation Controls and Data Model Study

> Purpose: turn ReconMatch from a stateless matcher into an auditable financial-control product. This is a research/design reference, not an implementation plan or compliance certification.

## Outcome

The system must prove five things for each reconciliation: the intended population arrived completely; source evidence was not silently altered; matching used an approved/versioned policy; exceptions were investigated under proper segregation of duties; and the resulting control was attested with durable evidence.

Basel’s risk-data principles require governance, data architecture, accuracy/integrity, completeness, timeliness, adaptability, reconciliation/validation, and documented manual workarounds. It also expects a single authoritative source per risk type where appropriate and exception reporting for data errors. [Basel SRP36](https://www.bis.org/basel_framework/chapter/SRP/36.htm)

## 1. Control model

```text
source delivery -> technical control -> data-quality control -> business matching
                -> exception workflow -> reviewer approval -> attestation/close
                                        -> audit evidence / reporting / journal proposal
```

| Control | Assertion | Evidence | Fail-safe behavior |
|---|---|---|---|
| Completeness | Every expected source partition arrived. | Calendar/expected feed, received object IDs, counts/totals. | Block auto-attestation; create source-control case. |
| Integrity | Evidence is authentic and unaltered after receipt. | Hash, source identity, receipt time, immutable object/version. | Quarantine or reject. |
| Validity | Values parse and conform to source contract. | Parser/mapping version, validation errors. | Quarantine affected rows; expose degraded scope. |
| Uniqueness | Re-delivery/duplicate business records do not multiply economics. | Idempotency key, duplicate cluster, decision. | Do not silently merge; record policy outcome. |
| Match correctness | A group satisfies an approved rule. | Candidate features, rule version, arithmetic, competing candidates. | Suggest/review rather than auto-match. |
| Authorization | Only permitted people/services act. | Identity, tenant scope, role/policy decision. | Deny by default. |
| Review | A prohibited self-approval cannot occur. | Maker/checker identities, action sequence. | Deny transition. |
| Close | Material exceptions/control failures are handled or formally accepted. | Attestation, open-break report, approval/evidence snapshot. | Keep period open. |

### Maker-checker rules

- A user who edits/activates a rule cannot solely approve that activation.
- A preparer cannot approve their own manual match, high-risk case, or attestation.
- An identity administrator cannot approve their own privileged access.
- A journal proposal must have a source case/policy and be independently approved before posting.
- Override/reopen actions always append an event; no actor may rewrite prior history.

These rules should be authorization constraints evaluated server-side, not UI conventions.

## 2. Data model: immutable layers

Do not overwrite a record while “cleaning” it. Store three representations:

```text
EvidenceObject (received bytes) -> SourceRecord (parsed source fields) -> CanonicalRecordVersion
```

| Object | Key fields | Immutability rule |
|---|---|---|
| `EvidenceObject` | ID, tenant, source system, URI, SHA-256, byte size, received time, retention class | Never replace bytes; supersede with new evidence object. |
| `SourceBatch` | source feed/message ID, expected partition, control totals, technical status | Append state events; keep raw delivery result. |
| `SourceRecord` | evidence ID/path/row, source record ID, raw payload, parse result | One per parsed row/message element. |
| `CanonicalRecordVersion` | canonical ID, version ID, normalized economics/identity/state, mapping version | New version for correction/remap; never in-place update. |
| `ReconciliationRun` | definition, scope, frozen input versions, reference snapshot, engine/rule versions | Immutable after completion; corrections are new runs/events. |

### Canonical financial record

Required columns, even if some are null for a first CSV connector:

```text
canonical_record_id, version_id, tenant_id, legal_entity_id, recon_definition_id,
source_system, source_account_or_book, source_record_id, evidence_id,
business_date, event_at_utc, booking_date, value_date, settlement_date,
currency, signed_minor_amount, signed_decimal_amount, quantity, price,
component_type, lifecycle_status, finality_status,
reference_ids (typed), counterparty_id, instrument_id, narrative_raw,
normalization_version, quality_status, created_at_utc
```

Amounts require both ISO currency and exact Decimal/minor-unit semantics. Preserve raw sign and record the mapping to the platform’s signed convention. Never infer a date from ingestion time when a business date is missing.

## 3. Match and allocation model

Replace a pair-only model with groups and allocations:

```text
MatchGroup(group_id, run_id, disposition, rule_version, confidence,
           currency, left_total, right_total, residual, explanation, timestamps)
MatchAllocation(group_id, record_version_id, side, allocated_minor_amount,
                allocated_quantity, component_role, allocation_method)
```

Invariants:

1. Each allocation references a frozen canonical record version.
2. Total allocations cannot exceed an available record capacity unless a policy explicitly supports reuse (normally it must not).
3. A group’s residual is exact, explicit, and classified; an unexplained residual never becomes an auto-match.
4. A 1:1 pair is just a group with two full allocations.
5. The explanation records predicates, normalized values, candidate alternatives, rule/configuration version, engine version, and arithmetic.

This supports 1:1, 1:N, N:1, N:M, partial allocation, net fees, FX, and component-based settlement without changing the audit model later.

## 4. Cases, tasks, and attestation

```text
BreakCase -> Task(s) -> ProposedResolution -> IndependentReview -> Resolved/Escalated
                                                          -> Attestation -> CloseLock
```

| Entity | Minimum fields |
|---|---|
| `BreakCase` | type, severity/materiality, linked records/groups, owner, SLA/due time, ageing, root-cause, resolution code, status. |
| `Task` | action, assignee/queue, maker/checker requirement, due time, completion evidence. |
| `EvidenceLink` | content hash, classification, retention/legal hold, redaction state, purpose. |
| `Attestation` | scope, preparer/reviewer, assertion, run/config/evidence snapshot hashes, open-exception disclosure, timestamp. |
| `JournalProposal` | debit/credit legs, entity/account dimensions, source case, policy, approval, ERP idempotency key, posting acknowledgement. |

Close locks the operational result. A correction creates a recorded reopen/adjustment event and a new attestation; it never erases a previous period’s evidence.

## 5. Audit event design

The business audit trail is separate from application/security logs but linked by correlation ID. Minimum event fields:

```text
event_id, aggregate_type, aggregate_id, sequence, tenant_id,
occurred_at_utc, actor_type, actor_id, request_id, correlation_id,
action, authorization_policy_version, before_hash, after_hash,
reason_code, evidence_ids, rule/config/engine versions, outcome
```

Use append-only storage; restrict mutation/deletion rights; periodically checkpoint/hash-chain events; retain a queryable projection separately from the write log. PCI’s logging intent is the ability to reconstruct who did what, where, when, and how. [PCI SSC](https://www.pcisecuritystandards.org/faqs/1081/)

Do not put credentials, secrets, full payment-card data, or unnecessary PII into events. OWASP ASVS requires useful investigation metadata and protection/masking appropriate to log-data sensitivity. [OWASP ASVS 5 logging](https://cornucopia.owasp.org/taxonomy/asvs-5.0/16-security-logging-and-error-handling/02-general-logging)

## 6. Scope, tenancy, and retention

Every durable object is scoped by tenant and, where applicable, legal entity, reconciliation definition, account/book, and data classification. Enforce tenant scope in every query/write/export—not only in a front-end filter.

Retention is a policy evaluated by `data_class + tenant/entity + jurisdiction + legal_hold`. GDPR requires purpose limitation, data minimisation, storage limitation, accuracy, integrity and confidentiality where it applies. [GDPR Article 5](https://eur-lex.europa.eu/legal-content/EN/TXT/?toc=OJ%3AL%3A2016%3A119%3AFULL&uri=uriserv%3AOJ.L_.2016.119.01.0001.01.ENG)

## 7. Phased implementation boundary

**First persistent cash MVP:** evidence objects, source batches/records, canonical cash versions, reconciliation run snapshot, match groups, break cases, basic maker-checker, audit events, and balance/control-total status.

**Before production:** SSO/MFA, server-side RBAC/SoD, encrypted object/database storage, secret manager, backup/restore drill, retention policy, observability, change approval, and attestation/close lock.

**Defer until data exists:** sophisticated risk scoring, ML-assisted matching, cross-domain schema generalization, and automatic journal posting.

## 8. Acceptance questions

- Can an auditor reproduce a result from retained evidence without trusting a mutable spreadsheet or application row?
- Can a duplicate file, late file, corrected file, and parser upgrade be distinguished?
- Can the same person activate and approve the same high-risk rule/match? The answer must be no.
- Can an unexplained difference be hidden by a net-zero group? The answer must be no.
- Can an attested period change without a new, attributable reopen event? The answer must be no.
