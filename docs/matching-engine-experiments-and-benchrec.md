# Matching Engine Experiments and BenchRec Study

> Goal: define a safe research programme for ReconMatch’s matching-signal gap and future N:M capability. This document does not authorize a production auto-match rule without measured precision and review evidence.

## 1. Current evidence

The local BenchRec baseline adapter records that the unmodified engine generates zero candidates/accepted matches on its evaluation data. Its documented causes are structural:

- tier 1 requires same date plus either exact reference or description similarity `>= 0.55`; obfuscated attributes do not clear the gate;
- tier 2 rejects same-date candidates by design;
- tier 3/4 are exact subset sums in a restricted date/sign/first-12 window;
- existing `SequenceMatcher`/token-containment is not the right primary signal for its character-obfuscated attribute text.

The data status record reports 32,048 B records, 31,836 matchable records, 212 true unmatched, and a practical 99.8% precision bar. Treat this as a separate external evaluation; do not tune the synthetic held-out set on it.

## 2. Hypotheses, in priority order

| ID | Hypothesis | Why it may help | Auto-match status initially |
|---|---|---|---|
| H1 | Same-date exact-amount candidates need a low-text path. | Most true pairs share value date; current tier 2 excludes them. | Review-only until precision measured. |
| H2 | Character n-gram/token features outperform current description score on obfuscated attributes. | Obfuscation preserves character fragments, not semantics. | Review-only. |
| H3 | Reference normalization rescues a subset of exact relations. | Structured/non-empty references may retain signal. | Can become deterministic if unique. |
| H4 | N:M exact groups recover multi-record cases after candidate generation is fixed. | BenchRec has N:M blocks, but cardinality alone cannot solve zero candidates. | Exact unique group only. |
| H5 | 1:1 amount tolerance recovers a limited non-exact population. | Status research records ~2.4% non-exact 1:1 train matches. | Deferred; policy-dependent. |

## 3. Evaluation protocol

### Splits and isolation

1. Use BenchRec `train` only to design features/rules and estimate thresholds.
2. Freeze all choices before a single `eval` score against the public solution.
3. Keep existing synthetic held-out seeds 100–149 unchanged as a regression test, not a tuning corpus.
4. Version data checksum, adapter, feature schema, rule/configuration, and solver/engine code for every run.

### Metrics

Report at B-transaction and match-group levels:

- coverage/recall among truly matchable B records;
- precision among predicted matches; financial false-positive count/value where data supports it;
- unmatched precision/recall for the 212 true-unmatched class;
- candidate blocking recall and mean/p95/p99 candidates per B;
- exact/low-text/fuzzy/N:M result breakdown;
- latency/memory/component size and timeout count;
- ambiguity rate: multiple plausible groups/candidates.

Optimize coverage subject to a predeclared precision constraint (initially 99.8% for the published benchmark), not aggregate F1 alone.

## 4. Experiment ladder

### E0 — data profiling, no matching change

Compute null/uniqueness/frequency distributions for amount, value date, references, attributes, signs, allocation cardinality, and duplicate attributes. Establish candidate-block sizes for `amount`, `(amount,date)`, `(amount,date,reference)`, and char-token keys. Confirm source/solution invariants and allocation conversion.

### E1 — deterministic same-date exact amount candidates

Generate `(amount, date)` candidates without a description gate. Classify each candidate as:

- unique (only one eligible A for B and one B for A);
- ambiguous (competing candidates);
- impossible/invalid scope.

Measure correctness of unique candidates before any text. If precision is below target, identify the discriminating fields required rather than lowering a threshold.

### E2 — character feature ablation

Inside E1 candidates, compare features individually and in interpretable combinations:

- normalized raw equality;
- q-gram Jaccard/cosine overlap (`q=2,3`);
- character edit ratio;
- token overlap after punctuation/digit normalization;
- prefix/suffix/reference agreement;
- amount/date exactness (always retained as hard features).

Use train only to select feature normalization/threshold/margin. Preserve every feature and candidate in a CSV/Parquet experiment artifact. Avoid semantic embeddings unless measured evidence beats character features with an explainable risk profile.

### E3 — conflict-aware 1:1 resolution

Build a sparse bipartite graph from eligible E2 candidates. Compare deterministic global greedy against maximum-weight bipartite assignment inside connected components. The Hungarian method addresses classical one-to-one assignment; shortest augmenting-path variants suit sparse/dense components. [Kuhn 1955](https://onlinelibrary.wiley.com/doi/pdfdirect/10.1002/nav.3800020109), [Jonker–Volgenant 1987](https://doi.org/10.1007/BF02278710)

Do not solve a global dense matrix. Partition by hard scope and split candidate graph into components. Route ties/low margins/large components to review.

### E4 — bounded N:M exact arithmetic

After E1–E3 generate viable links, introduce groups with exact amount conservation. Compare:

- cardinality 2–3 enumeration with pruning;
- meet-in-the-middle for bounded 1:N/N:1;
- N:M components with explicit allocation/flow formulation only where partial allocation is legitimate.

Subset sum has exponential worst-case behavior even with meet-in-the-middle improvements; budgets are a correctness control, not an optimization detail. [Subset-sum research](https://arxiv.org/abs/2301.07134)

### E5 — tolerance study, separately

Profile non-exact 1:1 amounts by absolute/relative difference, source type, date, text features, and apparent reason. Define named policies (rounding/known fee/FX) and estimate precision separately. Never bundle tolerance into fuzzy signal experiments; it changes financial semantics.

## 5. Candidate-engine reference design

```text
canonical records -> partition (scope/currency/sign/date) -> multi-key block indexes
                  -> candidate features -> component graph -> decision/optimizer
                  -> MatchGroup or suggestion/break -> experiment/audit artifact
```

Blocking avoids an all-pairs cross product and must be measured for link recall versus candidate reduction. [Michelson & Knoblock](https://cdn.aaai.org/AAAI/2006/AAAI06-070.pdf)

Required safeguards:

- Multiple block keys are unioned so one missing/dirty field does not destroy candidate recall.
- Each candidate stores the block reason and all feature values.
- Candidate per-record, component edge/node, group-cardinality, and wall-time budgets are versioned.
- Large/hot blocks become explicit ambiguity outcomes, not silent truncation (`[:12]` must be visible in production behavior).
- Amounts use exact minor units/Decimals; all residuals are explicit.
- Re-running frozen input/configuration yields byte-for-byte comparable result artifacts.

## 6. Proposed acceptance gates

| Stage | Gate |
|---|---|
| Candidate generation | Known train links have measured blocking recall; no unexplained truncation. |
| Exact 1:1 | Unique-candidate precision meets declared threshold on train before evaluation. |
| Low-text 1:1 | Train threshold and margin frozen; first eval is reported once, not tuned repeatedly. |
| N:M | Each accepted group is unique under bounds, conserves amounts, and has complete explanation. |
| Tolerance | Reason-specific policy, residual classification, and independent precision evidence. |
| Production | Human review feedback and source-quality monitoring continue to calibrate/disable rule versions. |

## 7. Recommended code boundaries

The current `engine.py` combines candidate enumeration, tier rules, and greedy resolution. Evolve it deliberately:

```text
normalization.py      pure/versioned feature transforms
blocking.py           indexes and candidate enumeration + metrics
rules.py              deterministic eligibility/disposition policy
graph.py              component construction and conflict representation
assignment.py         bounded 1:1 assignment / group resolver
explanations.py       stable result/evidence payload
experiments/benchrec  profiling, training, frozen-eval runner
```

Introduce each boundary with tests and golden candidates before replacing existing behavior. Do not tune the live synthetic matcher directly from a benchmark script.
