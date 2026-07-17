# ReconMatch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deterministic reconciliation-matching engine (bank-statement lines vs internal ledger) with confidence-scored matches, classified breaks, honest eval numbers, and a Gradio demo.

**Architecture:** Pure-function tiered matcher over Pydantic models with Decimal amounts. Synthetic datagen produces ledger/statement/truth triples; eval scores pair precision/recall and auto-match-rate@0.99-precision against truth. Gradio app on top; DocVal-JSON adapter for the end-to-end story.

**Tech Stack:** Python 3.12, Pydantic v2, uv, pytest, ruff, Gradio 6.x — mirror of ~/Projects/docval conventions (read its pyproject.toml, .github/workflows/ci.yml, Dockerfile, render.yaml for exact patterns).

## Global Constraints

- Repo root: `~/Projects/reconmatch` (local git; GitHub remote created later by Parvez — do NOT attempt `gh repo create`).
- All money is `decimal.Decimal`, never float. All dates are `datetime.date`.
- Amounts are signed: positive = money into the bank account (credit line / ledger receipt), negative = money out.
- Matching is deterministic: same inputs ⇒ same output, regardless of input order.
- The engine never reads ground truth; truth exists only in datagen output and eval.
- Every module lands with tests in the same task; commit after each task.
- Package layout: `src/reconmatch/…` with hatchling, same as docval.

---

### Task 1: Scaffold + schema

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `src/reconmatch/__init__.py`, `src/reconmatch/schema.py`
- Test: `tests/test_schema.py`

**Interfaces (Produces):**
```python
class LedgerEntry(BaseModel):  entry_id: str; date: datetime.date; description: str; amount: Decimal; reference: str | None = None
class StatementLine(BaseModel): line_id: str; date: datetime.date; description: str; amount: Decimal; reference: str | None = None
class MatchPair(BaseModel):    entry_id: str; line_ids: list[str]; tier: int; confidence: float
class Break(BaseModel):        side: Literal["ledger", "statement"]; record_id: str; category: Literal["missing_in_ledger", "missing_in_statement", "amount_mismatch_suspect", "duplicate_suspect"]; suggestion: str; related_id: str | None = None
class ReconReport(BaseModel):  matches: list[MatchPair]; breaks: list[Break]; summary: dict[str, float | int]
def load_ledger_csv(path: Path) -> list[LedgerEntry]      # columns: entry_id,date,description,amount[,reference]
def load_statement_csv(path: Path) -> list[StatementLine] # columns: line_id,date,description,amount[,reference]
```

- [ ] Step 1: `uv init --lib`-style pyproject copied from docval's shape (name reconmatch, deps: pydantic, gradio; dev: pytest, ruff). `uv sync --dev`.
- [ ] Step 2: Failing test: construct each model; CSV round-trip loaders reject float-looking parse only via Decimal("…"); malformed row raises `RowError` carrying row number.
```python
def test_ledger_csv_round_trip(tmp_path):
    p = tmp_path / "l.csv"
    p.write_text("entry_id,date,description,amount\nE1,2026-01-05,VENDOR PAYMENT,-1250.50\n")
    [e] = load_ledger_csv(p)
    assert e.amount == Decimal("-1250.50") and e.date == date(2026, 1, 5)

def test_malformed_row_reports_row_number(tmp_path):
    p = tmp_path / "l.csv"
    p.write_text("entry_id,date,description,amount\nE1,notadate,X,1.0\n")
    with pytest.raises(RowError) as ei:
        load_ledger_csv(p)
    assert ei.value.row == 2
```
- [ ] Step 3: Implement schema + loaders (csv module, `Decimal(raw)`, `date.fromisoformat`). Run tests → pass. `ruff check`.
- [ ] Step 4: Commit `feat: schema and CSV loaders`.

### Task 2: Synthetic datagen with ground truth

**Files:**
- Create: `src/reconmatch/datagen.py`
- Test: `tests/test_datagen.py`

**Interfaces (Produces):**
```python
class TruthPair(BaseModel): entry_id: str; line_ids: list[str]
class Truth(BaseModel): pairs: list[TruthPair]; breaks: list[Break]
def generate_pair(rng: random.Random, n_entries: int = 40) -> tuple[list[LedgerEntry], list[StatementLine], Truth]
def write_dataset(out_dir: Path, seed: int, n_entries: int = 40) -> None  # ledger.csv, statement.csv, truth.json
```

Perturbation mix (per entry, mutually exclusive, rng-driven): clean same-day 1:1 (p=.70), date lag 1–3 days (p=.10), split into 2–3 statement lines summing exactly (p=.08), amount digit typo on the statement side ⇒ amount_mismatch_suspect break (p=.04), entry missing from statement ⇒ missing_in_statement (p=.04). Statement-only extras appended afterwards: bank fee lines with no ledger entry ⇒ missing_in_ledger (2 per set), duplicated statement line ⇒ duplicate_suspect (1 per set). Descriptions from a vendor-name pool with statement-side mangling (uppercase, truncation to 18 chars, "POS " / "NEFT " prefixes) so tier-2 similarity is exercised.

- [ ] Step 1: Failing tests:
```python
def test_truth_covers_all_matchable_entries():
    ledger, lines, truth = generate_pair(random.Random(7))
    matched_entries = {p.entry_id for p in truth.pairs}
    break_ids = {b.record_id for b in truth.breaks}
    assert matched_entries | break_ids >= {e.entry_id for e in ledger}

def test_split_lines_sum_exactly():
    ledger, lines, truth = generate_pair(random.Random(7))
    by_id = {l.line_id: l for l in lines}
    for p in truth.pairs:
        entry = next(e for e in ledger if e.entry_id == p.entry_id)
        assert sum(by_id[i].amount for i in p.line_ids) == entry.amount

def test_deterministic_for_seed():
    a = generate_pair(random.Random(3)); b = generate_pair(random.Random(3))
    assert a[0] == b[0] and a[1] == b[1]
```
- [ ] Step 2: Implement; run; commit `feat: synthetic ledger/statement generator with truth`.

### Task 3: Engine tier 1 + greedy assignment skeleton

**Files:**
- Create: `src/reconmatch/engine.py`
- Test: `tests/test_engine.py`

**Interfaces (Produces):**
```python
class MatchConfig(BaseModel): date_window_days: int = 3; desc_threshold: float = 0.55; max_split: int = 3; near_miss_pct: Decimal = Decimal("0.01")
def desc_sim(a: str, b: str) -> float  # SequenceMatcher.ratio over casefolded strings
def match(ledger: list[LedgerEntry], lines: list[StatementLine], config: MatchConfig = MatchConfig()) -> list[MatchPair]
```

Internally `match` builds candidates from all tiers (later tasks add tiers 2–3), sorts by `(-confidence, tier, entry_id, tuple(line_ids))`, greedily accepts candidates whose entry and lines are all unused. Tier 1: same signed amount, same date, and (`reference` equal and non-None, or `desc_sim ≥ config.desc_threshold`) ⇒ confidence 0.95 + 0.05·(reference matched).

- [ ] Step 1: Failing tests: exact pair matches at conf ≥0.95; two identical-amount candidates resolve deterministically under input shuffle (property: `match(shuffled) == match(original)`); no line reused across pairs.
```python
def test_exact_match_and_determinism():
    e = LedgerEntry(entry_id="E1", date=d(5), description="ACME LTD INVOICE 44", amount=Decimal("-1250.50"))
    l = StatementLine(line_id="S1", date=d(5), description="POS ACME LTD", amount=Decimal("-1250.50"))
    [m] = match([e], [l])
    assert m.line_ids == ["S1"] and m.tier == 1 and m.confidence >= 0.95

def test_shuffle_invariance():
    ledger, lines, _ = generate_pair(random.Random(11))
    base = match(ledger, lines)
    rng = random.Random(0); shuffled_l = ledger[:]; rng.shuffle(shuffled_l)
    shuffled_s = lines[:]; rng.shuffle(shuffled_s)
    assert match(shuffled_l, shuffled_s) == base
```
- [ ] Step 2: Implement; commit `feat: tier-1 exact matcher with deterministic greedy assignment`.

### Task 4: Tier 2 windowed fuzzy matching

**Files:** Modify `src/reconmatch/engine.py`; test in `tests/test_engine.py`.

Tier 2 candidates: same signed amount, `0 < |date gap| ≤ date_window_days`, `desc_sim ≥ desc_threshold`. Confidence `0.6 + 0.3·sim·(1 − gap/(date_window_days+1))` (always < tier-1 confidences).

- [ ] Step 1: Failing tests: 2-day-lagged line matches at tier 2 with confidence in (0.6, 0.95); a same-amount line beyond the window does NOT match; tier 1 wins over tier 2 for the same entry.
- [ ] Step 2: Implement; commit `feat: tier-2 date-windowed matching`.

### Task 5: Tier 3 split (many-to-one) matching

**Files:** Modify `src/reconmatch/engine.py`; test in `tests/test_engine.py`.

For each unmatched-candidate entry, search combinations (size 2..max_split) of statement lines within the date window whose amounts sum exactly to the entry amount and share sign. Bound work: consider only the ≤12 window-eligible lines per entry, `itertools.combinations`. Confidence `0.55 + 0.15·mean(desc_sim) − 0.05·(k−2)`.

- [ ] Step 1: Failing tests: a 3-way split sums and matches with `line_ids` sorted; k>max_split does not match; split candidates lose to a tier-1 candidate competing for the same lines.
- [ ] Step 2: Implement; add the whole-engine property test on generated data:
```python
def test_engine_beats_truth_floor_on_generated_data():
    ledger, lines, truth = generate_pair(random.Random(42), n_entries=60)
    pred = {(m.entry_id, tuple(sorted(m.line_ids))) for m in match(ledger, lines)}
    gold = {(p.entry_id, tuple(sorted(p.line_ids))) for p in truth.pairs}
    precision = len(pred & gold) / len(pred)
    assert precision >= 0.95  # deterministic engine on clean synthetic data
```
- [ ] Step 3: Commit `feat: tier-3 split-payment matching`.

### Task 6: Break classification + suggestions

**Files:**
- Create: `src/reconmatch/breaks.py`
- Test: `tests/test_breaks.py`

**Interfaces (Produces):**
```python
def classify_breaks(ledger, lines, matches: list[MatchPair], config: MatchConfig) -> list[Break]
def reconcile(ledger, lines, config: MatchConfig = MatchConfig()) -> ReconReport  # match + classify + summary
```

Rules over unmatched residue, in order: (1) unmatched entry with an unmatched line in-window whose amount differs by ≤ near_miss_pct·|amount| or by digit transposition (string test: same digits multiset, same length, ≤2 positions differ) ⇒ `amount_mismatch_suspect` on the ledger side with `related_id`, suggestion names both amounts; (2) unmatched line equal in (date, amount, description) to any matched line ⇒ `duplicate_suspect`; (3) remaining unmatched lines ⇒ `missing_in_ledger` ("record this statement line in the ledger — e.g. bank fee"); (4) remaining unmatched entries ⇒ `missing_in_statement`. Summary: counts, match_rate (matched entries / entries), by-category break counts.

- [ ] Step 1: Failing tests: one handcrafted fixture per category asserting category, related_id, and that suggestions mention the amounts involved.
- [ ] Step 2: Implement; commit `feat: break classification and resolution suggestions`.

### Task 7: Eval — pair metrics, auto-match-rate@precision, regression gate

**Files:**
- Create: `eval/__init__.py`, `eval/metrics.py`, `eval/run_eval.py`, `eval/compare.py`, `eval/baseline_ci.json` (checked in after first run)
- Test: `tests/test_eval_metrics.py`

**Interfaces (Produces):**
```python
def pair_prf(pred: list[MatchPair], truth: Truth) -> dict          # precision/recall/f1 on (entry_id, sorted line_ids) pairs
def auto_match_rate(pred: list[MatchPair], truth: Truth, precision_floor: float = 0.99) -> dict
    # sweep confidence thresholds over pred; return highest fraction of truth pairs auto-accepted
    # with observed precision ≥ floor: {"rate": float, "threshold": float, "precision_at": float}
def break_prf(pred: list[Break], truth: Truth) -> dict             # per-category and micro F1 on (side, record_id, category)
# run_eval CLI: --seeds 100-149 --out DIR  → generates held-out sets, runs reconcile, writes aggregates JSON
# compare CLI: same contract as docval eval/compare.py (tracked keys: pair_f1, auto_match_rate, break_f1; tolerance 0.01)
```

Seed split convention: dev seeds 0–99, held-out seeds 100–149 — never tune on 100+.

- [ ] Step 1: Failing tests with tiny handcrafted pred/truth: perfect prediction ⇒ f1 1.0 and rate 1.0; one false match at high confidence caps auto_match_rate below 1.0; threshold returned actually achieves the floor.
- [ ] Step 2: Implement; run `uv run python -m eval.run_eval --seeds 100-149 --out eval/results` once; check in the aggregates as `eval/baseline_ci.json` (offline, deterministic, so CI can regenerate and compare cheaply).
- [ ] Step 3: CI workflow `.github/workflows/ci.yml`: copy docval's shape minus apt deps — pytest, ruff, then regenerate held-out eval and `eval/compare.py` against baseline.
- [ ] Step 4: Commit `feat: eval harness with auto-match-rate@0.99-precision + CI gate`.

### Task 8: DocVal adapter

**Files:**
- Create: `src/reconmatch/adapter.py`, `tests/fixtures/docval_sample.json` (copy `docval/samples/stmt_0000.result.json`)
- Test: `tests/test_adapter.py`

```python
def statement_lines_from_docval(extraction_json: dict) -> list[StatementLine]
# doc["doc"]["transactions"][i] → line_id f"T{i:04d}", date=txn_date, description, amount=credit−debit (Decimal, signed), reference=None
```

- [ ] Step 1: Failing test on the fixture: row count matches, a debit row comes out negative, Decimal type preserved.
- [ ] Step 2: Implement; commit `feat: DocVal extraction adapter`.

### Task 9: Gradio demo app

**Files:**
- Create: `app.py`, `samples/` (one generated ledger.csv + statement.csv + a precomputed report.json via datagen seed 100)
- Test: `tests/test_app.py`

Mirror docval `app.py` structure and hardening: two `gr.File` CSV inputs (≤1 MB each, must parse as CSV — reject with clean message, sanitized errors via a `public_error` twin), "Reconcile" button → matches dataframe (entry, lines, tier, confidence), breaks dataframe (side, id, category, suggestion), summary markdown; Samples tab loads the bundled pair instantly. All engine calls wrapped so malformed input returns a message, never a traceback.

- [ ] Step 1: Failing tests: `run_reconcile(ledger_path, statement_path)` returns non-empty tables on samples; malformed CSV path returns "❌" message not exception.
- [ ] Step 2: Implement; verify by launching locally and driving with `gradio_client` (samples + upload flow), same as docval verification.
- [ ] Step 3: Commit `feat: Gradio reconciliation demo`.

### Task 10: README + deploy scaffolding

**Files:**
- Create: `README.md`, `Dockerfile`, `render.yaml`, `.dockerignore`

README leads with the held-out numbers table (auto-match-rate@0.99-precision, pair F1, break F1 from Task 7's run), then the tier/confidence design, the DocVal end-to-end story, quickstart, and eval instructions. Dockerfile/render.yaml: copy docval's (drop apt pango deps; useradd BEFORE COPY — cache lesson learned). Deploy itself waits for the GitHub repo (Parvez) — Render service creation via API key is available once pushed.

- [ ] Step 1: Write files; `bash -n`-equivalent sanity (docker build unavailable locally — mirror the verified docval pattern).
- [ ] Step 2: Full `uv run pytest`, `ruff check`, commit `docs: README with held-out numbers + deploy scaffolding`.

---

## Self-review notes

- Spec coverage: schema/datagen/engine tiers/breaks/eval/adapter/app/README-deploy — all tasked. LLM-phrased suggestions are out (spec: off by default; YAGNI for v1 — rule-based strings only, noted in README as a flag-gated future).
- Types consistent: `MatchPair.line_ids: list[str]` everywhere; Truth reuses Break.
- Ambiguity: seed split convention pinned (dev 0–99, held-out 100–149).
