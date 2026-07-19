# ReconMatch Research and Development Map

> Last updated: 2026-07-20. This is the entry point for the research completed on 2026-07-19 and 2026-07-20.

## Reading order

| Order | Document | Use it for |
|---|---|---|
| 1 | [Industry-standard reconciliation architecture study](research/2026-07-19-industry-standard-reconciliation-architecture.md) | Platform scope, governance, end-to-end architecture, domain overlays, and phased roadmap. |
| 2 | [Transaction taxonomy and matching-engine design](research/2026-07-20-transaction-taxonomy-and-matching-engine-design.md) | Major transaction families, match types, candidate generation, scaling, assignment, N:M, and performance safety. |
| 3 | [Reconciliation controls and data model study](reconciliation-controls-and-data-model.md) | Persistent schema, immutable evidence, match groups, cases, SoD, audit, and attestation. |
| 4 | [Cash reconciliation domain and integrations study](cash-reconciliation-domain-and-integrations.md) | First production vertical: bank/ERP contracts, ISO mapping, balance/control totals, source recovery, and cash rules. |
| 5 | [Matching-engine experiments and BenchRec study](matching-engine-experiments-and-benchrec.md) | Evidence-driven work on same-date low-text matching, char features, N:M, tolerance, and benchmark discipline. |
| 6 | [Security and operational resilience baseline](security-and-operational-resilience-baseline.md) | Threat model, identity/authorization, uploads, audit logging, secure delivery, and recovery. |

## Supporting evidence registers

| Register | Covers |
|---|---|
| [Architecture source register](research/2026-07-19-source-register.md) | Basel, ISO 20022, Swift, SEC/PCAOB, NIST, PCI, GDPR, OWASP, and vendor-pattern material. |
| [Transaction/matching source register](research/2026-07-20-transaction-taxonomy-and-matching-engine-design-sources.md) | ISO transaction semantics and primary research on assignment, subset sum, blocking, and join algorithms. |

## Existing product specifications and plans

| Document | Current relevance |
|---|---|
| [Original product design](superpowers/specs/2026-07-17-reconmatch-artifact3-design.md) | Defines the first deterministic/stateless product slice. |
| [Original implementation plan](superpowers/plans/2026-07-17-reconmatch.md) | Historical implementation plan for the initial slice. |
| [N:1 batch matching design](superpowers/specs/2026-07-19-reconmatch-batch-match-design.md) | Shipped tier-4 batch matching design. |
| [N:1 batch matching plan](superpowers/plans/2026-07-19-reconmatch-batch-match.md) | Historical plan for the shipped N:1 feature. |

## How the documents map to development decisions

```text
controls + data model
       -> persistent evidence/runs/match groups/cases/audit
cash domain + integrations
       -> first vertical and source contracts
matching experiments
       -> validated low-text and N:M engine changes
security/resilience
       -> production access, safety, recovery gates
       -> workflow/attestation and controlled journals
```

## Recommended implementation research-to-build sequence

1. Convert the controls/data-model study into a single implementation plan for persistence, evidence, run snapshots, match groups, breaks/cases, audit, and basic workflow.
2. Plan bank/ERP ingestion and cash-population controls; retain the current CSV path as the first adapter.
3. Run the BenchRec experiment ladder without changing production matching policy; freeze a baseline and report results.
4. Implement the validated low-text/assignment/N:M work in bounded increments with golden tests and precision gates.
5. Complete production security/resilience controls before multi-tenant/customer financial data.

## Important boundaries

- These documents are architectural and technical research, not legal advice, a PCI/SOC/ISO certification, or a guarantee of regulatory compliance/security.
- No algorithm should auto-match a financial record solely because it has a high similarity score; policy, unique evidence, exact arithmetic, and measured precision control the decision.
- Do not build all listed transaction verticals at once. Cash is the intended first vertical; other domains require their own contracts and evaluation data.
