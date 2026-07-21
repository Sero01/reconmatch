"""FROZEN EVAL - the single held-out scoring run on BenchRec `eval`.

This is the one-shot run the plan reserves for the end of the ladder. It is run
ONCE, after all method decisions were fixed on `train` dev/val, so the number it
reports is honest held-out evidence rather than a tuned result.

Method under test: the E4 amount-cell component method (see groups.py) - records
partition into (currency, account, value_date, amount) cells; a cell with at
least one A and one B of opposite direction predicts, for each of its B's, the
SET of A allocations in that cell.

Scoring: strict exact-set, identical to groups.py. A B is correct iff its
COMPLETE predicted allocation set equals the solution's target set (both empty
counts as correct - a true-unmatched B that we correctly decline to match).

DISPOSITION: review-grade. Everything this method emits is SUGGESTED_FOR_REVIEW.
The 99.8% Wilson-LB auto bar was measured as UNREACHABLE on BenchRec (no
observable abstention predicate generalizes; the cross-amount join needed to
remove the dominant error class ceilings at ~26% reconstruction). No auto-match
is claimed here.

The MatcherByChatGPT reference submission is scored on the SAME B's under the
SAME scoring, so the comparison is like-for-like - unlike the earlier note that
compared train figures to eval figures.

Run:    uv run python experiments/benchrec/frozen_eval.py
Emits:  data/benchrec/artifacts/frozen_eval.md
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter, defaultdict

from bench_io import load_eval, load_solution, provenance_lines
from bench_stats import Z_95, wilson_lower_bound
from groups import DISPOSITION, build_components, parse_target, predict

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "..", "data", "benchrec")
EVAL = os.path.join(DATA, "BenchRec_cash_v1.0_eval.csv")
SOLUTION = os.path.join(DATA, "BenchRec_cash_v1.0_solution.csv")
REFERENCE = os.path.join(DATA, "MatcherByChatGPT_submission.csv")
ART = os.path.join(DATA, "artifacts")

csv.field_size_limit(sys.maxsize)


def load_reference(path: str) -> dict[str, frozenset[str]]:
    """B_id -> the reference matcher's PREDICTED allocation set.

    Its ``targetAllocation`` column is a JSON array; fall back to the plain
    bracket format, then to its single ``A_allocation`` pick.
    """
    out: dict[str, frozenset[str]] = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            raw = (row.get("targetAllocation") or "").strip()
            if raw:
                try:
                    parsed = json.loads(raw)
                    out[row["B_id"]] = frozenset(parsed) if isinstance(parsed, list) else frozenset([str(parsed)])
                    continue
                except (json.JSONDecodeError, ValueError):
                    out[row["B_id"]] = parse_target(raw)
                    continue
            alloc = (row.get("A_allocation") or "").strip()
            out[row["B_id"]] = frozenset([alloc]) if alloc else frozenset()
    return out


def stratum(target: frozenset[str]) -> str:
    if not target:
        return "true-unmatched"
    return "single-A" if len(target) == 1 else "multi-A"


def score(predictions: dict[str, frozenset[str]], truth: dict[str, frozenset[str]]) -> dict:
    """Strict exact-set scoring, stratified by target-set size."""
    stats: dict[str, Counter] = defaultdict(Counter)
    for b_id, target in truth.items():
        pred = predictions.get(b_id, frozenset())
        exact = pred == target
        for label in ("ALL", stratum(target)):
            stats[label]["n"] += 1
            stats[label]["exact"] += int(exact)
            if pred:
                stats[label]["emitted"] += 1
                stats[label]["emitted_exact"] += int(exact)
    return stats


def table(stats: dict, labels) -> list[str]:
    lines = [
        "| stratum | B records | emitted | exact | match rate | precision | Wilson 95% LB |",
        "|---|---|---|---|---|---|---|",
    ]
    for label in labels:
        c = stats.get(label)
        if not c:
            continue
        n, emitted, exact = c["n"], c["emitted"], c["emitted_exact"]
        rate = c["exact"] / n if n else 0.0
        prec = exact / emitted if emitted else 0.0
        lb = wilson_lower_bound(exact, emitted, Z_95) if emitted else 0.0
        lines.append(f"| {label} | {n:,} | {emitted:,} | {c['exact']:,} | "
                     f"{rate:.2%} | {prec:.2%} | {lb:.2%} |")
    return lines


def main() -> None:
    a_records, b_records = load_eval(EVAL)
    truth = {b_id: parse_target(raw) for b_id, raw in load_solution(SOLUTION).items()}

    cells = build_components({"A": a_records, "B": b_records})
    predictions: dict[str, frozenset[str]] = {}
    for cell in cells.values():
        if not cell["B"]:
            continue
        pred = predict(cell)
        if not pred:
            continue
        for b in cell["B"]:
            predictions[b.rec_id] = pred

    ours = score(predictions, truth)
    ref = score(load_reference(REFERENCE), truth)
    labels = ("ALL", "single-A", "multi-A", "true-unmatched")

    lines = [
        "# FROZEN EVAL - BenchRec `eval`, single held-out run",
        "",
        "> Generated by `experiments/benchrec/frozen_eval.py`. This is the ONE held-out scoring",
        "> run reserved by the plan. All method decisions were fixed on `train` dev/val before it",
        "> was executed, so these numbers are honest held-out evidence, not a tuned result.",
        "",
        "**Scoring: strict exact-set.** A B record is correct iff its COMPLETE predicted allocation",
        "set equals the solution's target set. Both-empty counts as correct (a true-unmatched B we",
        "correctly decline to match). Identical to the scoring used throughout the ladder.",
        "",
        f"**Disposition: `{DISPOSITION}` - review-grade.** The 99.8% Wilson-LB auto bar was measured",
        "as UNREACHABLE on BenchRec: no observable abstention predicate generalizes to held-out data",
        "(16/16 decision-tree configurations passed on dev and failed on val), and the cross-amount",
        "join needed to remove the dominant error class ceilings at ~26% reconstruction across 21",
        "configurations. **No auto-match is claimed.**",
        "",
        *provenance_lines(
            {"eval": EVAL, "solution": SOLUTION, "reference": REFERENCE},
            {"method": "E4 amount-cell components",
             "scoring": "strict exact-set (complete predicted set == target set)",
             "disposition": DISPOSITION,
             "tuning": "none on eval - all decisions fixed on train dev/val"},
        ),
        "",
        "## ReconMatch - amount-cell component method",
        "",
        *table(ours, labels),
        "",
        "## MatcherByChatGPT reference - same B's, same scoring",
        "",
        *table(ref, labels),
        "",
        "## Reading",
        "",
        "Both tables score the SAME B records under the SAME strict exact-set rule, so this is a",
        "like-for-like comparison - unlike the earlier train-vs-eval figure that was retracted.",
        "`match rate` is exact predictions over ALL B's in the stratum (the benchmark's headline",
        "quantity); `precision` and its Wilson lower bound are over the B's where a prediction was",
        "actually emitted.",
        "",
        "Caveat carried from the ladder: `train` is 27% N:M while `eval` multi-A is only ~5.6%, so",
        "the eval mix leans toward the 1:1 backbone relative to train.",
    ]

    os.makedirs(ART, exist_ok=True)
    out = os.path.join(ART, "frozen_eval.md")
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {out}\n")
    for name, stats in (("ReconMatch", ours), ("Reference ", ref)):
        for label in labels:
            c = stats.get(label)
            if not c:
                continue
            lb = wilson_lower_bound(c["emitted_exact"], c["emitted"], Z_95) if c["emitted"] else 0.0
            print(f"{name} | {label:<15} n={c['n']:>6,} exact={c['exact']:>6,} "
                  f"rate={c['exact'] / c['n']:>7.2%} precLB={lb:>7.2%}")
        print()


if __name__ == "__main__":
    main()
