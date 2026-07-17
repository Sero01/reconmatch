# ReconMatch

Reconciliation matching for financial ops: align bank-statement lines to
internal ledger entries, score every match with a confidence and the rule that
produced it, and classify every unmatched item as a **break** with a resolution
hint. The matcher is deterministic — same inputs, same output, zero inference
cost — so its numbers are reproducible and its decisions are auditable.

## Results (held-out, 50 synthetic sets, seeds 100–149, never tuned on)

| Metric | Value |
|---|---|
| **Auto-match rate @ ≥0.99 precision** | **95.4%** (observed precision 1.00) |
| Pair precision / recall / F1 | 1.00 / 0.95 / **0.98** |
| Break-classification precision / recall / F1 | 0.73 / 0.98 / **0.83** |

The headline is the one a reconciliation team actually buys: **95% of true
matches clear automatically with zero false matches**, leaving only the genuine
exceptions for a human. Break recall is high (0.98 — few real exceptions are
missed); break precision is lower (0.73) because the engine deliberately
over-flags amount-mismatch *suspects* rather than hide a possible error.

Numbers regenerate deterministically:

```bash
uv run python -m eval.run_eval --seeds 100-149
```

## How matching works

One deterministic pass. Every tier proposes candidates; they compete in a
single greedy assignment ordered by confidence, so a strong exact match always
beats a weaker split that wants to poach its lines. No line is ever used twice.

| Tier | Rule | Confidence |
|---|---|---|
| 1 — exact | same signed amount + same date + (reference match or description similarity ≥ 0.55) | 0.95–1.00 |
| 2 — windowed | same amount, date within ±3 days, description similarity ≥ 0.55 | 0.6–0.95, decaying with the date gap |
| 3 — split | 2–3 statement lines summing exactly to one ledger entry inside the window (partial/split payments) | ~0.55, decaying with split size |

Amounts are `Decimal` throughout (never float); positive = money into the
account, negative = money out. Descriptions are compared with a
char-ratio/token-containment blend, because banks mangle payee names (channel
prefixes, uppercasing, truncation).

## Breaks (the unmatched residue)

Everything left over is classified, in order: **amount-mismatch suspect**
(near-miss or digit transposition against an in-window line, both sides linked),
**duplicate suspect** (identical to an already-matched line), **missing in
ledger** (statement line with no ledger entry — the usual bank-fee case), and
**missing in statement** (ledger entry the bank never saw). Each carries a
plain-language suggestion naming the amounts involved.

## DocVal end to end

ReconMatch pairs with [DocVal](https://github.com/Sero01/docval): a statement
PDF flows extraction → validation → reconciliation. The adapter maps DocVal's
result JSON straight into statement lines (`credit − debit`, signed) with no
package dependency between the two repos:

```python
from reconmatch.adapter import statement_lines_from_docval
lines = statement_lines_from_docval(docval_result_json)
```

## Quickstart

```bash
uv sync --dev
uv run python app.py          # Gradio demo: bundled sample + two-CSV upload
uv run pytest                 # tests
uv run python -m eval.run_eval --seeds 100-149   # held-out metrics
```

CSV format for both inputs: `id,date,description,amount[,reference]`, amounts
signed. The demo ships a precomputed sample pair under `samples/`.

## Eval & regression gate

The eval harness scores reconciliation output against the generator's ground
truth: pair P/R/F1, break-classification F1, and the auto-match-rate sweep. It
is deterministic and offline, so CI regenerates the full held-out run on every
push and fails the build on any regression beyond a 0.01 tolerance against
`eval/baseline_ci.json`.

## Design notes

- Deterministic where it matters. An LLM is allowed only to *phrase* resolution
  suggestions, and that path is out of v1 (rule-based strings only) — matching
  itself never touches a model.
- Ground truth lives only in the generator and the eval; the engine never sees
  it.
- Out of scope (v1): ML-learned scoring, multi-currency FX matching, persistent
  state, auth, many-to-many matching beyond k ≤ 3 splits.

## Deploy

Dockerized Gradio app (`Dockerfile` + `render.yaml`), same shape as DocVal.
Live URL lands here once the repo is pushed and the Render service is created.
