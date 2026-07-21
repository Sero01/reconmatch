# E5 — Reaching (or bounding) the 99.8% auto bar on BenchRec

**Date:** 2026-07-21
**Status:** design, approved for implementation
**Scope:** `experiments/benchrec/` only. `src/reconmatch/` is untouched.

## Goal

Determine whether an **auto-match tier** can be carved out of the BenchRec
predictions that simultaneously satisfies:

| criterion | threshold |
|---|---|
| precision | Wilson 95% one-sided LB **>= 99.8%** |
| coverage | **>= 50% of all B records** |

Both must hold on the group-safe `val` split. Either the tier exists — the goal
is met — or we produce evidence that it cannot exist.

## Why this is being redone

The previous session reported two negative results that together closed this
goal: no abstention predicate generalizes (16/16 decision-tree configurations
passed on dev and failed on val), and the cross-amount join ceilings at ~24%
reconstruction. **Neither left any code, artifact table, or recorded
dependency** — `sklearn` is not in `pyproject.toml` and no script exists in the
repo or any scratchpad. Those findings are therefore treated as *unverified*,
not as wrong. A benchmark claim that cannot be reproduced is not a claim.

Additionally the prior work never stated a coverage floor, so "reach the auto
bar" was unfalsifiable: any precision target is trivially met by shrinking the
accepted set until only easy cases remain.

## Measurement protocol

- All work is measured on the **group-safe `train` dev/val split**
  (`assign_split`, matchId-hashed, `dev_frac=0.7`) — unchanged from E0–E4.
- The **`eval` split is spent** (one frozen run, 2026-07-21) and is **not
  touched again**. No number in this work is eval-derived.
- Selection happens on `dev`; `val` confirms. A predicate tuned on val is void.
- Scoring stays **strict exact-set**, identical to E4 and the frozen eval: a B
  is correct iff its complete predicted allocation set equals its target set.

## The target arithmetic

Dev shape-(1,1) components today: n=30,927, 224 errors, LB 99.19%.
Dev total B population: 48,297, so the 50% coverage floor is **24,149 B's**,
at which LB >= 99.8% permits roughly **<= 35 errors**.

Reaching the bar therefore requires removing ~189 of 224 errors while giving up
at most ~6,778 records — an error rate of ~2.8% inside the abstained set against
~0.11% in what remains, a **~25x discrimination lift**. This is the number the
work has to produce, and it is stated up front so the result is falsifiable.

## Approach

Two stages, run in order, because the first bounds what the second can buy.

### Stage 1 — Identifiability of the group partition

**The observation does not contain the answer.** At eval time the input is, per
record: `currency`, `account`, `valueDate`, `amount`, `direction`,
`transactionReferences`, `transactionAttributes`. `currency`, `account` and
`transactionType` are constants on BenchRec, so the entire observable space is
`amount`, `valueDate`, `direction` and two text fields. `matchId` — the group
partition, which *is* the label — is never observable.

Define a **legal partition**: a grouping of records in which every group has a
non-empty A side and B side, the two sides carry opposite directions, and the
group balances (`sum(A amounts) == sum(B amounts)`). The dataset's own true
partition is legal; so are others.

Define an **ambiguity witness** for a cell `C`: another legal partition of the
same date's records under which `C`'s B records belong to a strictly larger
group. The minimal construction is direct — if `C` is balanced and any *other*
balanced cell `C'` exists on the same date, then `C ∪ C'` is itself a legal
group. `C` alone and `C ∪ C'` are both fully consistent with every observable,
yet they imply *different correct answers* for every B in `C`.

Where a witness exists, **no function of the observables can decide the case**,
because two different correct answers share one input. This is an impossibility
result, not a failed search, and it is immune to "you did not try feature X".

Witnesses are computed at two strictness levels:

- **L1 — balance only.** As above.
- **L2 — balance + A-side token coherence.** 99.9% of true multi-amount groups
  share at least one token across all their A records, so a merge that breaks
  that regularity is one a text-aware method could in principle reject. L2
  requires the merged A side to share a token. Ambiguity surviving at L2 is the
  strong form of the result.

The same computation is constructive: cells with **no** witness are provably
unambiguous given the observables, and are exactly the principled auto-tier
candidates — safety by construction rather than by a fitted threshold. Stage 1
therefore reports both the impossibility fraction and the achievable auto tier,
scoring the witness-free set against the 50%/99.8% floor on dev and val.

### Stage 2 — Empirical frontier (gated on Stage 1)

Corroboration, and the answer to "did you actually try". Enumerate observable
feature families — pair, cell, date-neighborhood, global frequency, text,
combinatorial consistency — and fit a gradient-boosted classifier with a
group-safe split to predict per-prediction correctness, then plot the
**coverage-vs-Wilson-LB frontier** and mark the 50%/99.8% target.

Stage 1 sets the expectation Stage 2 must match: if the ambiguous fraction is
~all of the population, the frontier must fail, and a model that appears to
succeed is overfitting — the same failure mode as the unreproduced 16/16 result.
If Stage 1 leaves a large decidable residual, Stage 2 is the real work and runs
against that residual.

`sklearn` enters as an **experiments-only dependency group**. The production
package's runtime dependencies stay `gradio` + `pydantic`.

## Deliverables

| artifact | content |
|---|---|
| `experiments/benchrec/identifiability.py` | Stage 1, committed and reproducible |
| `data/benchrec/artifacts/e5_identifiability.md` | witness rates, auto-tier scoring vs the floor |
| `data/benchrec/artifacts/e5_witnesses.csv` | per-cell evidence: witness level, outcome, membership |
| `experiments/benchrec/frontier.py` | Stage 2, if Stage 1 leaves a residual |
| `data/benchrec/artifacts/e5_frontier.md` | coverage/LB frontier vs target |

Every artifact carries the standard provenance block (dataset SHA-256s, git
version, config, UTC timestamp) via `bench_io.provenance_lines`.

## Non-goals

- No production fold. That remains blocked on a MatchGroup/disposition/case
  model, and nothing here changes `src/reconmatch/`.
- No re-scoring of `eval`, for any reason.
- No cross-amount joining rule. Stage 1 determines whether one could exist at
  all; building one is out of scope for this spec.
