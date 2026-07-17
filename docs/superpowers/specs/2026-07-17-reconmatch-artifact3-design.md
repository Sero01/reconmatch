# ReconMatch — Artifact 3 Design: Reconciliation-Matching Demo

**Date:** 2026-07-17
**Status:** Drafted under autonomous /goal (Parvez to review; flag changes any time)
**Owner:** Parvez Ahmed

## Context

Artifact 3 of Strategic Roadmap v3 (weeks 6–8, pulled forward — Artifact 1
shipped ~3 weeks early). The roadmap's framing: *"AI-assisted transaction
matching with break-resolution workflow… your actual moat — TLM/SmartStream +
reconciliation ML experience is genuinely rare."* Together with DocVal the
story is: *"I turn messy financial documents into validated, reconciled data —
and I can prove the accuracy."*

Constraints (same as Artifact 1): synthetic/public data only, tests, live URL,
README that leads with numbers. New repo: `reconmatch` (created on Parvez's
GitHub when first push is due).

## Decisions made during (autonomous) brainstorming

- **Inputs:** two record sets — bank-statement lines and internal ledger
  entries — as CSV. A small adapter also accepts DocVal's extraction JSON, so
  a statement PDF can flow extraction → validation → reconciliation
  end-to-end. No hard dependency on the docval package; ReconMatch defines
  its own minimal schema.
- **Stack:** identical to DocVal (Python 3.12, Pydantic v2, uv, pytest, ruff,
  Gradio, GitHub Actions, Render Docker deploy). Consistency is a feature:
  the two repos read as one engineering hand.
- **The headline metric is ops-shaped:** *auto-match rate at ≥0.99 precision*
  — "how much manual matching work disappears while keeping false matches
  near zero." That's the number a reconciliation team actually buys, and no
  generic demo reports it. Standard pair-level precision/recall/F1 and
  break-classification accuracy sit underneath it.

## Approaches considered

1. **Deterministic tiered matcher with confidence scoring (chosen).**
   Interpretable, testable, zero inference cost, deterministic — the same
   properties that made DocVal's validation layer the differentiator. Every
   match carries an explainable confidence and the tier that produced it.
2. **ML classifier over pair features** (date gap, amount delta, description
   similarity → learned score). Stronger ceiling, but needs labeled pairs the
   synthetic generator would itself produce — circular training/eval on the
   same distribution, weak public proof. Deferred; the feature extraction in
   approach 1 is exactly the input a later classifier would need, so nothing
   is thrown away.
3. **LLM-judge matching.** Expensive, nondeterministic, and undermines the
   "deterministic where it matters" brand. Rejected for matching; an LLM is
   allowed only to *phrase* resolution suggestions, off by default.

## Architecture

```
ledger.csv ─┐
statement.csv ─┤→ schema (LedgerEntry / StatementLine, Decimal amounts)
(or DocVal JSON via adapter) ─┘
  └─ match engine (tiered, deterministic):
       tier 1  exact: amount + date + reference/description token overlap
       tier 2  windowed: amount exact, date within ±3 days (default),
               description similarity ≥ 0.55 → confidence f(sim, gap)
       tier 3  many-to-one: k ≤ 3 unmatched statement lines summing to one
               ledger amount inside the date window (split payments)
       greedy assignment in confidence order; deterministic tie-breaks
  └─ break classifier (unmatched residue):
       missing-in-ledger / missing-in-statement / amount-mismatch-suspect
       (near-miss within small delta → suggests fee or transposition) /
       duplicate-suspect
  └─ suggestion engine: rule-based resolution text per break category
       (optional LLM phrasing behind a flag, default off)
  └─ ReconReport: matches w/ confidence + tier, breaks w/ category +
       suggestion, summary stats
```

### Modules

| Module | Responsibility |
|---|---|
| `schema.py` | LedgerEntry, StatementLine, MatchPair, Break, ReconReport |
| `datagen/generate.py` | Synthetic ledger+statement pairs with known truth: date lag, bank fees, partial/split payments, missing entries, duplicates, digit-typo amounts |
| `match/engine.py` | The three tiers + greedy assignment; pure functions |
| `match/breaks.py` | Break classification + rule-based suggestions |
| `adapter.py` | DocVal extraction JSON → StatementLine[] |
| `eval/` | Pair-level P/R/F1 vs ground truth, break-class accuracy, auto-match-rate@0.99-precision; CI regression gate (compare.py pattern from DocVal) |
| `app.py` | Gradio: two CSV uploads or bundled samples → match table, break list, summary; same hardening as DocVal (size caps, magic-byte/CSV sniffing, sanitized errors) |

## Data flow & error handling

- All amounts are `Decimal`; row parsing failures are per-row findings, never
  crashes — a malformed CSV row becomes a reported break-input error.
- The matcher never throws on content: worst case everything lands unmatched
  with honest breaks.
- Ground truth lives only in datagen output (`truth.json` beside each pair);
  the engine never sees it.

## Testing

- TDD per module; property-style tests for the engine (e.g., matching is
  symmetric in confidence ranking, deterministic under shuffle, never matches
  the same line twice).
- Eval fixtures: small handcrafted ledger/statement pairs with known breaks
  covering every category.
- CI: pytest + ruff + offline eval regression gate against a committed
  baseline, from day one.

## Success criteria (mirrors Artifact 1)

- Live URL a stranger can use with bundled samples.
- README leading with: auto-match rate @ 0.99 precision, pair F1,
  break-classification accuracy, on a held-out synthetic set (generator
  seeds split dev/held-out; held-out never tuned on).
- Green Actions badge; the DocVal→ReconMatch end-to-end story demonstrated
  with one sample statement.

## Out of scope (v1)

ML-learned scoring, multi-currency FX matching, persistent state/database,
authentication, many-to-many matching beyond k≤3 splits.
