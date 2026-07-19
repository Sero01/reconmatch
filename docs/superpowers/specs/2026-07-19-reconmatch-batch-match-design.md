# ReconMatch — Batch Matching (N:1) Design

**Date:** 2026-07-19
**Status:** Approved by Parvez (interactive brainstorm)
**Extends:** `2026-07-17-reconmatch-artifact3-design.md` (which listed matching
"beyond k≤3 splits" as out of scope for v1 — this is the deliberate v2 step)

## Problem

The engine matches 1:1 (tiers 1–2) and 1:N — one ledger entry settled by
several statement lines (tier 3). The reverse, **N:1 — several ledger entries
settled by one statement line — is unhandled**, yet it is the more common
direction in practice: payroll runs (one "SALARY BATCH" debit covering many
per-employee entries), bulk supplier payments, gross batch settlements.

Today those cases degrade into a confident misdiagnosis: the batch line is
reported `missing_in_ledger` ("bank fees and interest are the usual
culprits") and each component entry `missing_in_statement` ("payment may have
failed"). Both suggestions are wrong, which undercuts the breaks layer's
whole pitch. Independent confirmation the gap is real: BenchRec (ICAIF 2023,
Tier-1 production recon data) defines its task as one statement entry
matching ledger entrie**s**, plural.

## Decisions (made 2026-07-19)

1. **Scope: N:1 now, BenchRec later.** This change ships evaluated on
   extended synthetic data only. BenchRec becomes a separate follow-up after
   its schema and license are inspected (Kaggle download required).
2. **Schema: generalize `MatchPair`.** `entry_id: str` → `entry_ids:
   list[str]`. One shape covers 1:1, 1:N, N:1 (and N:M someday). The repo is
   live (GitHub + Render demo) but nothing external consumes the report
   JSON shape, so the breaking change costs one deploy; a second
   `BatchMatch` type was rejected as permanent two-shape complexity
   everywhere downstream.
3. **Sum rule: exact only.** Mirrors tier 3. Gross batches are caught
   deterministically with no new false-positive risk. Net-of-fee settlements
   keep falling to the breaks layer (see Future work).

## Approach

A mirrored **tier 4** — `_tier3` with the roles swapped. Rejected
alternatives: unifying tiers 3+4 into one bidirectional function (the
direction parameter costs more readability than ~25 duplicated lines; plain
tier functions are the repo's style) and a grouping-key batch detector
(scales past k≤3 but is a different algorithm shape — noted as the future
path if `max_split` ever needs to grow).

## Changes by module

### `schema.py`
- `MatchPair.entry_id: str` → `entry_ids: list[str]`. Nothing else changes.

### `engine.py`
- Tiers 1–3 emit `entry_ids=[entry.entry_id]`.
- New `_tier4(line, entries, config)`: candidate ledger entries within
  `date_window_days` of the line, same sign, capped at 12 (same bound as
  tier 3); combinations of k = 2..`max_split` whose amounts sum **exactly**
  to `line.amount`; confidence `0.55 + 0.15·avg_sim − 0.05·(k−2)` — same
  family as tier 3.
- **No similarity floor** for tier 4: batch lines ("SALARY BATCH") share no
  tokens with per-entry descriptions; sims only shape confidence. At equal
  confidence the existing sort breaks ties by tier number, so a tier-3 split
  outranks a tier-4 batch.
- Greedy resolver: both uniqueness checks become set intersections
  (`used_entries & set(cand.entry_ids)`); sort keys use `tuple(entry_ids)`.
  Invariants preserved: every entry and every line used at most once;
  candidates from all tiers compete in one deterministic confidence-ordered
  pass, so a strong exact match always beats a batch trying to poach its
  records.

### `breaks.py`
- `matched_entries` becomes the union over `entry_ids` (one line). Gross
  batches now match upstream, so the misdiagnosis described above
  disappears for them.

### `datagen.py`
- New scenario branch, ~6 % of the roll, carved from the 70 % clean-1:1
  band: 2–3 ledger entries (distinct vendors, nearby dates) settled by one
  statement line whose amount is their exact sum, with a bank-style batch
  description ("BULK PAYMENT", "NEFT BATCH SETTLEMENT").
- `TruthPair.entry_id` → `entry_ids: list[str]`.
- This scenario is what makes the feature provable rather than merely
  present; the engine never sees truth, as before.

### `eval/metrics.py`
- Match key becomes `(tuple(sorted(entry_ids)), tuple(sorted(line_ids)))` in
  `_pair_keys` and `auto_match_rate`.
- **`eval/baseline_ci.json` is regenerated.** The datagen distribution
  changes, so old baseline numbers are meaningless; the regression gate
  resets against the new distribution — stated plainly in the commit.

### `app.py`
- "Ledger entry" column renders `", ".join(entry_ids)`, mirroring how
  line_ids already render.

### Untouched
- `adapter.py` and the DocVal wire format.

## Testing (TDD, per repo convention)

New: a gross payroll batch matches at tier 4; an exact 1:1 beats an
overlapping batch candidate; no entry/line double-use across tiers 3+4;
deterministic output under input shuffle; sign guard (mixed-sign combos
never batch). Updated: every existing test touching `entry_id`, eval
fixtures, break classification post-batch.

## Out of scope now / Future work (Parvez will say when)

- **1:1 tolerance matching** — auto-match a single entry to a single line
  whose amounts differ within a small tolerance (FX rounding, absorbed
  fees), at discounted confidence. Industry tools do most of their tolerance
  work at 1:1; multi-record matches stay exact-sum, where tolerance would
  multiply subset-sum coincidences. Today these pairs surface only as
  `amount_mismatch_suspect` breaks. **Deferred — implement when Parvez says.**
- **User-specified custom match rules** — user-defined matching criteria
  (e.g. field equalities, tolerances, date windows per rule) layered onto or
  ahead of the built-in tiers. **Deferred — implement when Parvez says.**
- Fee-tolerant / net-of-fee batch settlements (needs a fee hypothesis, a
  separately designed feature).
- N:M matching; grouping-key batch detection for large batches (k > 3).
- BenchRec adapter + eval (follow-up: download from Kaggle, check license
  permits public README metrics; obfuscated descriptions may neuter
  `desc_sim`, exercising amount/date logic only).
