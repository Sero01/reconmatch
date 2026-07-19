# ReconMatch N:1 Batch Matching (Tier 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Match several ledger entries settled by one statement line (payroll runs, bulk supplier payments) as a fourth deterministic tier, ending today's misdiagnosis of gross batches as missing-record breaks.

**Architecture:** Generalize `MatchPair.entry_id: str` → `entry_ids: list[str]` so one shape covers 1:1, 1:N, N:1. Add `_tier4` to the engine — a mirror of `_tier3` with the roles swapped (candidate ledger entries in the date window, same sign, exact subset-sum, k ≤ `max_split`). Candidates from all four tiers compete in the existing single greedy confidence-ordered pass. Datagen grows a batch scenario so the feature is provable; the eval baseline resets because the data distribution changes.

**Tech Stack:** Python 3.12, Pydantic v2, uv, pytest, ruff. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-19-reconmatch-batch-match-design.md`

## Global Constraints

- Repo root: `/home/parvez/Projects/reconmatch`, branch `master`. Run everything with `uv run`.
- All money is `Decimal`, signed: positive = into the bank account, negative = out.
- The engine is deterministic: same inputs (any order) → same output. Never break this.
- Sum rule for multi-record matches is **exact equality** — no tolerance anywhere in this plan.
- Tier-4 confidence family: `0.55 + 0.15·avg_sim − 0.05·(k−2)`; **no similarity floor** for tier 4.
- The engine never sees datagen truth.
- `eval/baseline_ci.json` is regenerated in Task 4 (seeds 100-149) — CI regenerates the same run and compares, so the new baseline must land in the same push as the engine change.
- Do NOT implement: 1:1 tolerance matching, custom match rules, fee-tolerant batches, N:M (spec future work — Parvez will say when).

---

### Task 1: Generalize `MatchPair`/`TruthPair` to `entry_ids` (mechanical rename, no behavior change)

Everything currently keying on `m.entry_id` moves to `m.entry_ids: list[str]`. After this task the full suite is green and eval numbers are **identical** to before (tiers 1–3 each emit a one-element list; datagen distribution untouched).

**Files:**
- Modify: `src/reconmatch/schema.py` (MatchPair)
- Modify: `src/reconmatch/engine.py` (emit sites, sort keys, greedy resolver)
- Modify: `src/reconmatch/breaks.py` (matched_entries, summary)
- Modify: `src/reconmatch/datagen.py` (TruthPair only)
- Modify: `eval/metrics.py` (pair keys)
- Modify: `app.py` (match table row + header)
- Modify: `tests/test_schema.py`, `tests/test_engine.py`, `tests/test_eval_metrics.py`, `tests/test_datagen.py`
- Regenerate: `samples/report.json` (serialized old shape; `show_sample()` validates it against the new schema)

**Interfaces:**
- Produces: `MatchPair(entry_ids: list[str], line_ids: list[str], tier: int, confidence: float)`; `TruthPair(entry_ids: list[str], line_ids: list[str])`; eval match key `(tuple(sorted(entry_ids)), tuple(sorted(line_ids)))`. Tasks 2–4 rely on exactly these.

- [ ] **Step 1: Update the schema and its test**

In `src/reconmatch/schema.py` replace the MatchPair class:

```python
class MatchPair(BaseModel):
    entry_ids: list[str]
    line_ids: list[str]
    tier: int
    confidence: float
```

In `tests/test_schema.py`, `test_models_construct`, replace the MatchPair line:

```python
    m = MatchPair(entry_ids=["E1"], line_ids=["S1", "S2"], tier=3, confidence=0.61)
```

- [ ] **Step 2: Run the suite to see the blast radius**

Run: `uv run pytest -x -q`
Expected: FAIL — ValidationError / AttributeError in engine, breaks, eval, app tests (`entry_id` no longer exists). This is the checklist for the next steps.

- [ ] **Step 3: Update engine emit sites and resolver**

In `src/reconmatch/engine.py`:

`_tier1` return:
```python
        return MatchPair(entry_ids=[entry.entry_id], line_ids=[line.line_id],
                         tier=1, confidence=1.0)
```
(and the description-similarity return just below it: same change, `confidence=0.95`)

`_tier2` return:
```python
    return MatchPair(entry_ids=[entry.entry_id], line_ids=[line.line_id],
                     tier=2, confidence=confidence)
```

`_tier3` append:
```python
            out.append(MatchPair(
                entry_ids=[entry.entry_id],
                line_ids=sorted(c.line_id for c in combo),
                tier=3, confidence=confidence))
```

In `match()`, the candidate sort, greedy pass, and final sort:
```python
    candidates.sort(key=lambda m: (-m.confidence, m.tier, tuple(m.entry_ids),
                                   tuple(m.line_ids)))
    used_entries: set[str] = set()
    used_lines: set[str] = set()
    accepted: list[MatchPair] = []
    for cand in candidates:
        if used_entries & set(cand.entry_ids) or used_lines & set(cand.line_ids):
            continue
        used_entries.update(cand.entry_ids)
        used_lines.update(cand.line_ids)
        accepted.append(cand)
    accepted.sort(key=lambda m: tuple(m.entry_ids))
    return accepted
```

- [ ] **Step 4: Update breaks.py**

In `classify_breaks`:
```python
    matched_entries = {eid for m in matches for eid in m.entry_ids}
```

In `reconcile`:
```python
    n_matched = len({eid for m in matches for eid in m.entry_ids})
```

- [ ] **Step 5: Update datagen TruthPair and its emit sites**

In `src/reconmatch/datagen.py`:
```python
class TruthPair(BaseModel):
    entry_ids: list[str]
    line_ids: list[str]
```

Both `pairs.append(...)` calls in the 1:1/lagged branches become:
```python
            pairs.append(TruthPair(entry_ids=[entry.entry_id],
                                   line_ids=[line.line_id]))
```
The split branch becomes:
```python
            pairs.append(TruthPair(entry_ids=[entry.entry_id], line_ids=ids))
```

- [ ] **Step 6: Update eval keys**

In `eval/metrics.py`:
```python
def _pair_keys(pairs) -> set:
    return {(tuple(sorted(p.entry_ids)), tuple(sorted(p.line_ids)))
            for p in pairs}
```
and in `auto_match_rate`:
```python
        accepted = [(tuple(sorted(m.entry_ids)), tuple(sorted(m.line_ids)))
                    for m in pred if m.confidence >= t]
```

- [ ] **Step 7: Update app match rendering**

In `app.py`:
```python
MATCH_HEADERS = ["Ledger entries", "Statement line(s)", "Tier", "Confidence"]
```
and in `_render`:
```python
    matches = [[", ".join(m.entry_ids), ", ".join(m.line_ids), m.tier,
                round(m.confidence, 3)]
               for m in report.matches]
```

- [ ] **Step 8: Update remaining test callsites**

`tests/test_engine.py`, `test_engine_precision_floor_on_generated_data`:
```python
def test_engine_precision_floor_on_generated_data():
    ledger, lines, truth = generate_pair(random.Random(42), n_entries=60)
    pred = {(tuple(sorted(m.entry_ids)), tuple(sorted(m.line_ids)))
            for m in match(ledger, lines)}
    gold = {(tuple(sorted(p.entry_ids)), tuple(sorted(p.line_ids)))
            for p in truth.pairs}
    assert pred, "engine matched nothing"
    precision = len(pred & gold) / len(pred)
    assert precision >= 0.95, precision
```

`tests/test_eval_metrics.py` — `_truth` and `_pair` helpers:
```python
def _truth():
    return Truth(
        pairs=[
            TruthPair(entry_ids=["E1"], line_ids=["S1"]),
            TruthPair(entry_ids=["E2"], line_ids=["S2", "S3"]),
        ],
        breaks=[],
    )


def _pair(entry_id, line_ids, confidence, tier=1):
    return MatchPair(entry_ids=[entry_id], line_ids=line_ids, tier=tier,
                     confidence=confidence)
```
and `test_returned_threshold_actually_achieves_floor`'s key lines:
```python
    gold = {(tuple(sorted(p.entry_ids)), tuple(sorted(p.line_ids)))
            for p in truth.pairs}
    accepted = [m for m in pred if m.confidence >= r["threshold"]]
    correct = sum((tuple(sorted(m.entry_ids)), tuple(sorted(m.line_ids))) in gold
                  for m in accepted)
```

`tests/test_datagen.py` — two truth-accounting tests:
```python
def test_truth_accounts_for_every_ledger_entry():
    ledger, lines, truth = generate_pair(random.Random(7))
    matched = {i for p in truth.pairs for i in p.entry_ids}
    broken = {b.record_id for b in truth.breaks if b.side == "ledger"}
    assert matched | broken == {e.entry_id for e in ledger}
    assert matched.isdisjoint(broken)
```
and replace `test_split_lines_sum_exactly` with the direction-agnostic version (works for 1:1, 1:N, and — after Task 3 — N:1):
```python
def test_pair_amounts_balance_exactly():
    ledger, lines, truth = generate_pair(random.Random(7))
    by_id = {line.line_id: line for line in lines}
    entries = {e.entry_id: e for e in ledger}
    for p in truth.pairs:
        total_lines = sum(by_id[i].amount for i in p.line_ids)
        total_entries = sum(entries[i].amount for i in p.entry_ids)
        assert total_lines == total_entries, p
```

- [ ] **Step 9: Regenerate samples/report.json (same CSVs, new wire shape)**

```bash
uv run python - <<'EOF'
from pathlib import Path
from reconmatch.breaks import reconcile
from reconmatch.schema import load_ledger_csv, load_statement_csv
report = reconcile(load_ledger_csv(Path("samples/ledger.csv")),
                   load_statement_csv(Path("samples/statement.csv")))
Path("samples/report.json").write_text(report.model_dump_json(indent=2))
EOF
```

- [ ] **Step 10: Full suite green, lint clean**

Run: `uv run pytest -q && uv run ruff check`
Expected: all tests PASS (same count as before: 44), no lint errors.

- [ ] **Step 11: Prove eval numbers are unchanged**

```bash
uv run python -m eval.run_eval --seeds 100-149 --out /tmp/t1_eval
uv run python -m eval.compare /tmp/t1_eval/*.json eval/baseline_ci.json
```
Expected: `no regressions` — the rename must not move any metric.

- [ ] **Step 12: Commit**

```bash
git add -A
git commit -m "refactor: generalize MatchPair.entry_id to entry_ids list

Mechanical rename across engine, breaks, datagen truth, eval keys, app
rendering, and samples/report.json. Tiers 1-3 emit one-element lists;
behavior and eval numbers unchanged. Prepares for N:1 batch tier."
```

---

### Task 2: Tier 4 — exact-sum batch matching in the engine (TDD)

**Files:**
- Modify: `src/reconmatch/engine.py` (module docstring, `_tier4`, `match()` loop)
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `MatchPair(entry_ids=..., line_ids=..., tier=..., confidence=...)` from Task 1.
- Produces: tier-4 `MatchPair`s with `entry_ids` = sorted ids of 2..`max_split` ledger entries, `line_ids` = one statement line, `tier=4`, confidence `0.55 + 0.15·avg_sim − 0.05·(k−2)`. Task 3's datagen scenario must be recoverable by exactly this.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_engine.py` (the `entry`/`line` helpers at the top of the file already exist):

```python
# --- tier 4 ---

def test_batch_settlement_matches_tier4():
    entries = [
        entry("E1", desc="Global Talent Payroll invoice 101", amount="-40000.00"),
        entry("E2", desc="Kavya Consulting invoice 102", amount="-15500.25"),
        entry("E3", desc="Omega IT Services invoice 103", amount="-8200.75"),
    ]
    batch = line("S1", desc="NEFT BATCH SETTLEMENT", amount="-63701.00")
    [m] = match(entries, [batch])
    assert m.tier == 4
    assert m.entry_ids == ["E1", "E2", "E3"]
    assert m.line_ids == ["S1"]
    assert m.confidence < 0.95


def test_exact_match_beats_batch_poaching():
    # E1 has an exact tier-1 partner; a batch wanting E1 must not steal it.
    e1 = entry("E1", amount="-100.00")
    e2 = entry("E2", desc="Kavya Consulting invoice 9", amount="-50.00")
    s1 = line("S1", amount="-100.00")
    s2 = line("S2", desc="BULK PAYMENT", amount="-150.00")
    ms = match([e1, e2], [s1, s2])
    assert len(ms) == 1
    [m] = ms
    assert m.entry_ids == ["E1"] and m.line_ids == ["S1"] and m.tier == 1


def test_entry_used_once_across_tiers():
    e1 = entry("E1", amount="-100.00")
    e2 = entry("E2", desc="Kavya Consulting invoice 9", amount="-60.00")
    s_batch = line("S1", desc="BULK PAYMENT", amount="-160.00")
    s_exact = line("S2", amount="-100.00")
    ms = match([e1, e2], [s_batch, s_exact])
    used = [eid for m in ms for eid in m.entry_ids]
    assert len(used) == len(set(used))


def test_mixed_sign_never_batches():
    e1 = entry("E1", amount="-100.00")
    e2 = entry("E2", desc="Customer refund 7", amount="50.00")
    s = line("S1", desc="BULK PAYMENT", amount="-50.00")
    assert match([e1, e2], [s]) == []


def test_batch_beyond_max_k_no_match():
    entries = [entry(f"E{i}", desc=f"Vendor {i} invoice {i}", amount="-25.00")
               for i in range(1, 5)]
    s = line("S1", desc="BULK PAYMENT", amount="-100.00")
    assert match(entries, [s], MatchConfig(max_split=3)) == []
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_engine.py -q -k "tier4 or poaching or used_once or mixed_sign or beyond_max_k"`
Expected: `test_batch_settlement_matches_tier4` FAILS (no match produced — no tier generates it); the poaching/used-once/mixed-sign/beyond-max tests may pass vacuously — confirm at least the first fails.

- [ ] **Step 3: Implement `_tier4` and wire it into `match()`**

In `src/reconmatch/engine.py`, add after `_tier3`:

```python
def _tier4(line: StatementLine, ledger: list[LedgerEntry],
           config: MatchConfig) -> list[MatchPair]:
    """One statement line settling 2..max_split ledger entries (gross batch)."""
    window = [
        e for e in ledger
        if abs((e.date - line.date).days) <= config.date_window_days
        and (e.amount < 0) == (line.amount < 0)
    ][:12]  # bound the combination search
    out = []
    for k in range(2, config.max_split + 1):
        for combo in combinations(window, k):
            if sum(e.amount for e in combo) != line.amount:
                continue
            # batch lines ("SALARY BATCH") rarely echo entry descriptions,
            # so similarity shapes confidence but is never a gate here
            sims = [desc_sim(e.description, line.description) for e in combo]
            confidence = 0.55 + 0.15 * (sum(sims) / len(sims)) - 0.05 * (k - 2)
            out.append(MatchPair(
                entry_ids=sorted(e.entry_id for e in combo),
                line_ids=[line.line_id],
                tier=4, confidence=confidence))
    return out
```

In `match()`, after the per-entry candidate loop, add:

```python
    for line in lines:
        candidates.extend(_tier4(line, ledger, config))
```

Update the module docstring's tier list (first paragraph) to:

```python
"""Deterministic tiered matching of ledger entries to statement lines.

Tier 1: same signed amount, same date, reference equality or description
        similarity. Tier 2: same amount inside a date window. Tier 3:
        2..max_split statement lines summing exactly to one entry. Tier 4:
        2..max_split ledger entries summing exactly to one statement line
        (gross batch settlements).
Candidates from every tier compete in one deterministic greedy pass
ordered by confidence, so a strong exact match always beats a split
or batch that wants to poach its records.
"""
```

- [ ] **Step 4: Run the new tests, then the full suite**

Run: `uv run pytest tests/test_engine.py -q` then `uv run pytest -q && uv run ruff check`
Expected: all PASS. If `test_engine_precision_floor_on_generated_data` regresses (<0.95): tier 4 is producing false batches on data that has none — inspect the false positives before touching thresholds; the fix should be in candidate generation, never in loosening the test.

- [ ] **Step 5: Prove eval numbers still unchanged (no batches in data yet)**

```bash
uv run python -m eval.run_eval --seeds 100-149 --out /tmp/t2_eval
uv run python -m eval.compare /tmp/t2_eval/*.json eval/baseline_ci.json
```
Expected: `no regressions`. Tier 4 on batch-free data should be near-silent; a precision drop here means false batches — stop and inspect per Step 4.

- [ ] **Step 6: Commit**

```bash
git add src/reconmatch/engine.py tests/test_engine.py
git commit -m "feat: tier 4 - N:1 exact-sum batch matching

Mirror of tier 3 with roles swapped: 2..max_split same-sign ledger
entries in the date window summing exactly to one statement line. No
similarity floor (batch descriptions rarely echo entries); candidates
compete in the same greedy pass, so exact matches can't be poached."
```

---

### Task 3: Datagen batch scenario + truth (TDD)

**Files:**
- Modify: `src/reconmatch/datagen.py` (entry-id helper refactor + batch branch)
- Test: `tests/test_datagen.py`, plus rerun of engine/breaks suites

**Interfaces:**
- Consumes: `TruthPair(entry_ids=..., line_ids=...)` from Task 1; tier-4 matchability from Task 2 (same sign, dates within window, exact sum, k ≤ 3).
- Produces: `generate_pair` where ~6 % of rolls emit 2–3 ledger entries settled by one batch line. Task 4's baseline reset assumes this distribution.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_datagen.py`:

```python
def test_batch_settlements_present_at_scale():
    ledger, lines, truth = generate_pair(random.Random(5), n_entries=200)
    batches = [p for p in truth.pairs if len(p.entry_ids) > 1]
    assert batches, "no batch scenarios generated"
    assert all(len(p.line_ids) == 1 for p in batches)
    entries = {e.entry_id: e for e in ledger}
    for p in batches:
        signs = {entries[i].amount < 0 for i in p.entry_ids}
        assert len(signs) == 1, f"mixed-sign batch {p}"
```

(The amount identity for batches is already covered by `test_pair_amounts_balance_exactly` from Task 1 — sum of entry amounts equals sum of line amounts for every pair, whichever side is plural.)

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_datagen.py -q`
Expected: `test_batch_settlements_present_at_scale` FAILS with "no batch scenarios generated".

- [ ] **Step 3: Refactor entry creation and add the batch branch**

In `src/reconmatch/datagen.py`, add a module-level constant after `_PREFIXES`:

```python
_BATCH_DESCS = ["BULK PAYMENT", "NEFT BATCH SETTLEMENT", "SALARY BATCH"]
```

In `generate_pair`, mirror the existing `new_line` helper with one for entries, replacing the direct `LedgerEntry(...)` construction (ids keep the `E%04d` format but come from a counter, so a batch can mint extra entries mid-iteration):

```python
    entry_no = 0

    def new_entry(d: date, desc: str, amount: Decimal) -> LedgerEntry:
        nonlocal entry_no
        entry_no += 1
        e = LedgerEntry(entry_id=f"E{entry_no:04d}", date=d,
                        description=desc, amount=amount)
        ledger.append(e)
        return e
```

The main loop header becomes `for _ in range(n_entries):` and the entry construction becomes:

```python
        entry = new_entry(d, f"{vendor} invoice {rng.randint(100, 999)}", amount)
```

Re-band the roll — clean 1:1 shrinks from 70 % to 64 %, batch takes 6 %, everything downstream keeps its width:

```python
        roll = rng.random()
        if roll < 0.64:  # clean same-day 1:1
            line = new_line(d, desc, amount)
            pairs.append(TruthPair(entry_ids=[entry.entry_id],
                                   line_ids=[line.line_id]))
        elif roll < 0.70:  # gross batch: this entry + 1-2 more -> one line
            batch = [entry]
            for _ in range(rng.randint(1, 2)):
                v2 = VENDORS[rng.randrange(len(VENDORS))]
                a2 = _amount(rng)
                if (a2 < 0) != (amount < 0):
                    a2 = -a2  # gross batches are same-sign by definition
                batch.append(new_entry(
                    d + timedelta(days=rng.randrange(2)),
                    f"{v2} invoice {rng.randint(100, 999)}", a2))
            total = sum(e.amount for e in batch)
            bline = new_line(d + timedelta(days=rng.randrange(2)),
                             _BATCH_DESCS[rng.randrange(len(_BATCH_DESCS))],
                             total)
            pairs.append(TruthPair(
                entry_ids=[e.entry_id for e in batch],
                line_ids=[bline.line_id]))
        elif roll < 0.80:  # settles 1-3 days later
            ...
```
(the `elif roll < 0.80` / `< 0.88` / `< 0.92` / `else` branches keep their existing bodies, with the two `TruthPair` emit sites already updated in Task 1).

- [ ] **Step 4: Run datagen tests, then the whole suite**

Run: `uv run pytest tests/test_datagen.py -q` then `uv run pytest -q && uv run ruff check`
Expected: all PASS. Watch `test_engine_precision_floor_on_generated_data` and `test_shuffle_invariance` specifically — they now run against data containing batches. A precision failure means the engine mis-batches (inspect the false positive); a shuffle failure means tier 4 broke determinism (check the sort keys).

- [ ] **Step 5: Sanity-check the engine actually recovers generated batches**

```bash
uv run python - <<'EOF'
import random
from reconmatch.datagen import generate_pair
from reconmatch.engine import match

hit = total = 0
for seed in range(100, 150):
    ledger, lines, truth = generate_pair(random.Random(seed))
    pred = {(tuple(sorted(m.entry_ids)), tuple(sorted(m.line_ids)))
            for m in match(ledger, lines)}
    for p in truth.pairs:
        if len(p.entry_ids) > 1:
            total += 1
            hit += (tuple(sorted(p.entry_ids)), tuple(sorted(p.line_ids))) in pred
print(f"batch recall on held-out: {hit}/{total} = {hit/total:.2%}")
EOF
```
Expected: a majority recovered (>60 %). Some misses are legitimate (a batch whose combination window exceeds the 12-candidate cap, or whose exact sum collides with a stronger candidate). If near zero, tier 4 and the generator disagree on window/sign — debug before proceeding.

- [ ] **Step 6: Commit**

```bash
git add src/reconmatch/datagen.py tests/test_datagen.py
git commit -m "feat: datagen gross-batch scenario (6% of rolls)

2-3 same-sign ledger entries settled by one bank-style batch line
summing exactly; truth records the N:1 pair. Entry ids now come from a
counter so batches mint extra entries mid-roll."
```

---

### Task 4: Baseline reset, samples, app copy, README

**Files:**
- Regenerate: `eval/baseline_ci.json`, `samples/ledger.csv`, `samples/statement.csv`, `samples/report.json`
- Modify: `app.py` (two Markdown strings), `README.md` (matching description + metrics)

**Interfaces:**
- Consumes: the new datagen distribution (Task 3) and tier-4 engine (Task 2). Nothing downstream consumes this task.

- [ ] **Step 1: Regenerate the held-out baseline**

```bash
uv run python -m eval.run_eval --seeds 100-149 --out /tmp/t4_eval
cat /tmp/t4_eval/*.json | uv run python -c "import json,sys; d=json.load(sys.stdin); print(json.dumps(d['aggregates'], indent=2))"
```
Then write `eval/baseline_ci.json` with the fresh aggregates in the existing file's exact shape — `seeds`/`n_sets`/`n_entries` keys unchanged, `note` updated:

```json
{
  "seeds": "100-149",
  "n_sets": 50,
  "n_entries": 40,
  "note": "deterministic offline held-out run; CI regenerates and compares. Baseline reset 2026-07-19: datagen adds gross-batch scenario (spec 2026-07-19), so pre-batch numbers are not comparable.",
  "aggregates": { }
}
```
(fill `aggregates` with the printed values verbatim — every key `run_eval` tracks, same order as the old file). Sanity: `pair_precision` and `auto_match_precision` should stay ≥ 0.99; recall/rate may move either way vs the old file — that is expected and fine. If `pair_precision` fell below 0.99, tier 4 is producing false batches: stop and inspect before committing anything.

- [ ] **Step 2: Verify the gate passes against the new baseline**

```bash
uv run python -m eval.compare /tmp/t4_eval/*.json eval/baseline_ci.json
```
Expected: `no regressions` (it is comparing a run to a baseline built from that run — this verifies file shape and the compare path, exactly what CI will execute).

- [ ] **Step 3: Regenerate samples with a batch in them**

The demo sample should show off the new tier. Same recipe as the original samples (datagen seed 100, per `docs/superpowers/plans/2026-07-17-reconmatch.md`), which now contains batch rolls:

```bash
uv run python - <<'EOF'
from pathlib import Path
from reconmatch.breaks import reconcile
from reconmatch.datagen import write_dataset
from reconmatch.schema import load_ledger_csv, load_statement_csv

write_dataset(Path("samples"), seed=100)
(Path("samples") / "truth.json").unlink()  # samples ship without truth
report = reconcile(load_ledger_csv(Path("samples/ledger.csv")),
                   load_statement_csv(Path("samples/statement.csv")))
Path("samples/report.json").write_text(report.model_dump_json(indent=2))
tier4 = [m for m in report.matches if m.tier == 4]
print(f"tier-4 matches in sample: {len(tier4)}")
EOF
```
Expected: `tier-4 matches in sample:` ≥ 1. If 0, seed 100's rolls produced no batch — try seeds 101, 102, … and use the first that yields one (record the chosen seed in the commit message).

- [ ] **Step 4: Update app copy**

In `app.py`, the intro Markdown:

```python
    gr.Markdown("# ReconMatch\nMatches bank-statement lines to internal ledger "
                "entries — exact, date-windowed, split payments, and batch "
                "settlements — then classifies every unmatched item as a "
                "break with a resolution hint. Deterministic: same inputs, "
                "same output, zero inference cost.")
```

and the sample-tab Markdown:

```python
        gr.Markdown("A synthetic 40-entry ledger against its bank statement "
                    "(date lags, split payments, batch settlements, bank "
                    "fees, a keying error, a duplicate).")
```

- [ ] **Step 5: Update README matching description and metrics**

In `README.md`: wherever the tier list / matching description appears, add tier 4 ("2..3 ledger entries settled by one statement line, exact sum — gross batch settlements"); update the metrics table/lead numbers to the Step 1 aggregates; note the baseline reset date and reason in one line ("Baseline reset 2026-07-19: datagen now includes gross-batch settlements"). Read the file first and match its existing tone — numbers first, no hedging.

- [ ] **Step 6: Full suite + lint one last time**

Run: `uv run pytest -q && uv run ruff check`
Expected: all PASS, lint clean.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: baseline reset + samples/app/README for batch matching

eval/baseline_ci.json regenerated (datagen distribution changed with
the gross-batch scenario; pre-batch numbers not comparable). Samples
regenerated to include a tier-4 batch; app and README copy updated."
```

- [ ] **Step 8: Push (CI is the final gate)**

```bash
git push origin master
```
Then watch the Actions run (`gh run watch` or the repo's Actions tab): pytest, ruff, and the eval gate must all pass. Render redeploys from master — after CI is green, load the live demo's sample tab and confirm a Tier 4 row renders.

---

## Self-review notes

- Spec coverage: schema ✓ (T1), engine tier 4 + resolver ✓ (T2), breaks one-liner ✓ (T1 Step 4 — the union *is* the spec's breaks change), datagen ✓ (T3), eval keys ✓ (T1) + baseline reset ✓ (T4), app ✓ (T1 render + T4 copy), adapter untouched ✓ (no task touches it), all five spec test cases ✓ (T2 Steps 1, T3 Step 4 covers shuffle-with-batches).
- Deliberate deviation from spec wording: the spec's "no similarity floor" is honored; tier ordering at equal confidence favors lower tier via the existing sort — asserted implicitly by `test_exact_match_beats_batch_poaching`.
- Baseline regeneration happens twice as a *check* (T1/T2 prove nothing moved) and once as a *reset* (T4) — the distinction is the point.
