"""Generate held-out synthetic sets, reconcile them, write aggregate metrics.

Fully deterministic and offline: each seed reproduces the same ledger/statement
pair and the same match output, so CI can regenerate this run and compare it to
a committed baseline without any network or model calls.

Seed convention: dev 0-99, held-out 100-149. Never tune on 100+.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
from pathlib import Path

from reconmatch.breaks import reconcile
from reconmatch.datagen import generate_pair

from eval.metrics import auto_match_rate, break_prf, pair_prf

TRACKED = ("pair_precision", "pair_recall", "pair_f1", "auto_match_rate",
           "auto_match_precision", "break_precision", "break_recall",
           "break_f1", "engine_match_rate")


def evaluate(seeds: list[int], n_entries: int = 40) -> dict:
    per_set = []
    for seed in seeds:
        ledger, lines, truth = generate_pair(random.Random(seed), n_entries)
        report = reconcile(ledger, lines)
        pp = pair_prf(report.matches, truth)
        amr = auto_match_rate(report.matches, truth)
        bp = break_prf(report.breaks, truth)
        per_set.append({
            "seed": seed,
            "n_entries": len(ledger), "n_lines": len(lines),
            "pair_precision": pp["precision"], "pair_recall": pp["recall"],
            "pair_f1": pp["f1"],
            "auto_match_rate": amr["rate"],
            "auto_match_precision": amr["precision_at"],
            "auto_match_threshold": amr["threshold"],
            "break_precision": bp["precision"], "break_recall": bp["recall"],
            "break_f1": bp["f1"],
            "engine_match_rate": report.summary["match_rate"],
        })

    def mean(key: str) -> float:
        return sum(r[key] for r in per_set) / len(per_set) if per_set else 0.0

    return {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "seeds": f"{seeds[0]}-{seeds[-1]}" if seeds else "",
        "n_sets": len(per_set),
        "n_entries": n_entries,
        "aggregates": {key: mean(key) for key in TRACKED},
        "per_set": per_set,
    }


def parse_seeds(spec: str) -> list[int]:
    """Accept '100-149' ranges (inclusive) or '1,4,9' comma lists."""
    if "-" in spec:
        lo, hi = spec.split("-")
        return list(range(int(lo), int(hi) + 1))
    return [int(s) for s in spec.split(",")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="100-149")
    ap.add_argument("--n-entries", type=int, default=40)
    ap.add_argument("--out", type=Path, default=Path("eval/results"))
    args = ap.parse_args()
    results = evaluate(parse_seeds(args.seeds), args.n_entries)
    args.out.mkdir(parents=True, exist_ok=True)
    stamp = results["timestamp"].replace(":", "-")
    out_file = args.out / f"{stamp}.json"
    out_file.write_text(json.dumps(results, indent=2))
    print(json.dumps(results["aggregates"], indent=2))
    print("wrote", out_file)


if __name__ == "__main__":
    main()
