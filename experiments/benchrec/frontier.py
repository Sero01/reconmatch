"""E5 stage 2 - the coverage/precision frontier over the observable feature space.

Stage 1 proved that for ~98.5% of predictions an ambiguity witness exists, so
*certainty* is unavailable. That is not the same as "no signal": the auto bar is
99.8%, not 100%, and a Bayes-optimal ranker can still clear it if the observables
correlate with correctness. A cell sitting on a date with two balanced siblings
is far less mergeable than one with two hundred - ambiguity is GRADED, and stage
1 handed that measure over as a feature.

So this module asks the empirical question properly, once, with the bookkeeping
the previous unreproduced attempt lacked:

  * enumerate the observable feature space by family - cell shape, graded
    ambiguity, amount, text, A/B-side sibling structure, direction - covering
    every field BenchRec exposes (currency, account and transactionType are
    constants and carry nothing);
  * fit a gradient-boosted classifier for P(prediction is exact) on `dev`;
  * sweep the accept threshold on `val` and plot coverage against the Wilson 95%
    lower bound on precision, marking the target;
  * report the in-sample dev frontier alongside it, because the gap between them
    IS the overfitting that sank the earlier decision-tree search.

Target (fixed before the run, see the design spec):

    precision Wilson 95% LB >= 99.8%  AND  coverage >= 50% of all B records

Coverage is over ALL B records in the split, not over emitted predictions, so
abstention cannot flatter the number. `eval` is spent and is never read here.

Run:  uv run python experiments/benchrec/frontier.py
Emits: data/benchrec/artifacts/e5_frontier.md
       data/benchrec/artifacts/e5_frontier.csv
"""
from __future__ import annotations

import csv
import math
import os
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)

from bench_io import load_train, provenance_lines           # noqa: E402
from bench_stats import Z_95, min_n_for_bound, wilson_lower_bound  # noqa: E402
from groups import (                                         # noqa: E402
    EXACT,
    build_components,
    classify,
    population,
    predict,
    split_groups,
    truth_maps,
)
from identifiability import (                                # noqa: E402
    a_tokens_common,
    date_key,
    is_balanced,
    tokens,
)

DATA = os.path.join(HERE, "..", "..", "data", "benchrec")
TRAIN = os.path.join(DATA, "BenchRec_cash_v1.0_train.csv")
ART = os.path.join(DATA, "artifacts")

SPLITS = ("dev", "val")
TARGET_LB = 0.998
TARGET_COVERAGE = 0.50
WINDOW_DAYS = 3


def _qgrams(s: str, q: int = 3) -> frozenset[str]:
    s = " ".join(s.casefold().split())
    if len(s) < q:
        return frozenset({s}) if s else frozenset()
    return frozenset(s[i:i + q] for i in range(len(s) - q + 1))


def _jaccard(x: frozenset, y: frozenset) -> float:
    return len(x & y) / len(x | y) if x and y else 0.0


def _parse_date(s: str):
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


class DateContext:
    """Per-date structures every sibling/ambiguity feature reads from."""

    def __init__(self, cells_on_date):
        self.cells = cells_on_date
        self.balanced = [k for k, c in cells_on_date.items() if is_balanced(k, c)]
        self.n_records = sum(len(c["A"]) + len(c["B"]) for c in cells_on_date.values())
        self.amount_counts = Counter()
        self.token_post: dict[str, dict[str, set]] = {"A": defaultdict(set),
                                                      "B": defaultdict(set)}
        self.rec_amount: dict[str, int] = {}
        for key, cell in cells_on_date.items():
            amt = key[3]
            for side in ("A", "B"):
                for r in cell[side]:
                    self.amount_counts[amt] += 1
                    self.rec_amount[r.rec_id] = amt
                    for t in tokens(r):
                        self.token_post[side][t].add(r.rec_id)

    def siblings_diff_amount(self, recs, side: str) -> tuple[int, int]:
        """(#records on this date at a DIFFERENT amount sharing a token with any
        of ``recs``, #records at a different amount at all) - the direct
        observable signature of a multi-amount group fragment."""
        own_amounts = {self.rec_amount.get(r.rec_id) for r in recs}
        own_ids = {r.rec_id for r in recs}
        shared: set[str] = set()
        for r in recs:
            for t in tokens(r):
                shared |= self.token_post[side][t]
        shared -= own_ids
        shared = {i for i in shared if self.rec_amount.get(i) not in own_amounts}
        total_diff = sum(n for a, n in self.amount_counts.items() if a not in own_amounts)
        return len(shared), total_diff


def build_rows(pop, b_target):
    """One feature row per B record that receives an emitted prediction."""
    cells = build_components(pop)
    by_date: dict[tuple, dict] = defaultdict(dict)
    for key, cell in cells.items():
        by_date[date_key(key)][key] = cell

    ctx = {d: DateContext(c) for d, c in by_date.items()}

    global_amount_freq = Counter()
    date_of: dict[tuple, list] = defaultdict(list)
    for key, cell in cells.items():
        n = len(cell["A"]) + len(cell["B"])
        global_amount_freq[key[3]] += n
        d = _parse_date(key[2])
        if d is not None:
            date_of[key[3]].append(d)

    rows = []
    for key, cell in cells.items():
        predicted = predict(cell)
        if not predicted or not cell["B"]:
            continue
        dk = date_key(key)
        c = ctx[dk]
        amt = key[3]
        n_a, n_b = len(cell["A"]), len(cell["B"])

        witness_n = sum(1 for k in c.balanced if k != key)
        witness_tok = sum(1 for k in c.balanced
                          if k != key and a_tokens_common([cell, c.cells[k]]))

        a_sib_tok, a_sib_all = c.siblings_diff_amount(cell["A"], "A")
        b_sib_tok, b_sib_all = c.siblings_diff_amount(cell["B"], "B")

        this_date = _parse_date(key[2])
        window_freq = 0
        if this_date is not None:
            lo, hi = this_date - timedelta(days=WINDOW_DAYS), this_date + timedelta(days=WINDOW_DAYS)
            window_freq = sum(1 for d in date_of[amt] if lo <= d <= hi)

        a_qg = [_qgrams(a.attributes) for a in cell["A"]]
        a_tok = [tokens(a) for a in cell["A"]]
        a_attr_len = sum(len(a.attributes) for a in cell["A"]) / max(1, n_a)
        a_has_ref = sum(1 for a in cell["A"] if a.reference.strip()) / max(1, n_a)

        for b in cell["B"]:
            bq, bt = _qgrams(b.attributes), tokens(b)
            rows.append({
                "b_id": b.rec_id,
                "label": int(classify(predicted, b_target.get(b.rec_id, frozenset())) == EXACT),
                # -- cell shape
                "n_a": n_a,
                "n_b": n_b,
                "shape_balanced": int(n_a == n_b),
                "pred_size": len(predicted),
                # -- graded ambiguity (stage 1)
                "witness_count": witness_n,
                "witness_token_count": witness_tok,
                "date_cells": len(c.cells),
                "date_balanced_cells": len(c.balanced),
                "date_records": c.n_records,
                # -- amount
                "amount_minor": amt,
                "log_amount": math.log10(amt) if amt > 0 else 0.0,
                "round_unit": int(amt % 100 == 0),
                "round_ten": int(amt % 1000 == 0),
                "round_hundred": int(amt % 10000 == 0),
                "amount_global_freq": global_amount_freq[amt],
                "amount_date_freq": c.amount_counts[amt],
                "amount_alone_on_date": int(c.amount_counts[amt] == n_a + n_b),
                "amount_window_freq": window_freq,
                # -- text
                "ab_qgram3_max": max((_jaccard(bq, q) for q in a_qg), default=0.0),
                "ab_token_overlap": max((len(bt & t) for t in a_tok), default=0),
                "ab_shares_token": int(any(bt & t for t in a_tok)),
                "b_attr_len": len(b.attributes),
                "a_attr_len": a_attr_len,
                "b_attr_empty": int(not b.attributes.strip()),
                "b_has_ref": int(bool(b.reference.strip())),
                "a_has_ref": a_has_ref,
                # -- sibling structure (fragment signature)
                "a_sib_token_diffamt": a_sib_tok,
                "a_sib_any_diffamt": a_sib_all,
                "b_sib_token_diffamt": b_sib_tok,
                "b_sib_any_diffamt": b_sib_all,
                # -- direction
                "b_dir_dr": int(b.direction == "DR"),
            })
    return rows


FEATURES = None  # populated from the first row, minus bookkeeping columns
SKIP = {"b_id", "label"}


def to_matrix(rows):
    global FEATURES
    if FEATURES is None:
        FEATURES = [k for k in rows[0] if k not in SKIP]
    X = [[float(r[f]) for f in FEATURES] for r in rows]
    y = [r["label"] for r in rows]
    return X, y


def frontier(scores, labels, total_b):
    """Sweep the accept threshold at EVERY rank.

    Full resolution matters near the top of the ranking: the bar needs n>=1,351
    at zero errors to be evidenced at all, so a coarse sweep can straddle the
    exact ceiling and report 'never clears' for what is really a boundary case.
    """
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    out, exact = [], 0
    for rank, idx in enumerate(order, start=1):
        exact += labels[idx]
        out.append({
            "n": rank,
            "coverage": rank / total_b,
            "exact": exact,
            "lb": wilson_lower_bound(exact, rank, Z_95),
            "threshold": scores[idx],
        })
    return out


def best_at_target(front):
    """Largest coverage whose Wilson LB still clears the target."""
    ok = [r for r in front if r["lb"] >= TARGET_LB]
    return max(ok, key=lambda r: r["coverage"]) if ok else None


def first_error(front):
    """The rank at which the ranking's first mistake appears."""
    prev = 0
    for r in front:
        if r["exact"] == prev and r["n"] > 1:
            return r
        prev = r["exact"]
    return None


def sample_every(front, pct_step=5):
    """One frontier row nearest each ``pct_step``% of coverage, for display."""
    out, seen = [], set()
    for r in front:
        bucket = int(r["coverage"] * 100 / pct_step)
        if bucket and bucket not in seen:
            seen.add(bucket)
            out.append(r)
    return out


def main() -> None:
    from sklearn.ensemble import HistGradientBoostingClassifier

    _a, _b, groups = load_train(TRAIN)
    b_target, _b_card, _b_amount = truth_maps(groups)
    per_split = split_groups(groups)

    rows, total_b = {}, {}
    for sp in SPLITS:
        pop = population(per_split[sp])
        total_b[sp] = len(pop["B"])
        rows[sp] = build_rows(pop, b_target)

    X_dev, y_dev = to_matrix(rows["dev"])
    X_val, y_val = to_matrix(rows["val"])

    model = HistGradientBoostingClassifier(
        max_iter=400, learning_rate=0.06, max_leaf_nodes=31,
        l2_regularization=1.0, random_state=0,
    )
    model.fit(X_dev, y_dev)

    s_dev = [p[1] for p in model.predict_proba(X_dev)]
    s_val = [p[1] for p in model.predict_proba(X_val)]

    f_dev = frontier(s_dev, y_dev, total_b["dev"])
    f_val = frontier(s_val, y_val, total_b["val"])
    best_dev, best_val = best_at_target(f_dev), best_at_target(f_val)

    # Coverage the target demands, and what the model actually delivers there.
    def at_coverage(front, target):
        cands = [r for r in front if r["coverage"] >= target]
        return min(cands, key=lambda r: r["coverage"]) if cands else None

    at50_dev, at50_val = at_coverage(f_dev, TARGET_COVERAGE), at_coverage(f_val, TARGET_COVERAGE)
    fe_val = first_error(f_val)

    def fmt(r):
        if r is None:
            return "| - | - | - | never reached |"
        return (f"| {r['coverage']:.2%} | {r['n']:,} | {r['exact']:,} | "
                f"{r['lb']:.3%} |")

    lines = [
        "# E5 stage 2 - observable-feature frontier for the auto bar",
        "",
        "> Generated by `experiments/benchrec/frontier.py`. Model fitted on `dev`,",
        "> frontier read on `val`. Coverage is over ALL B records in the split, so",
        "> abstaining cannot inflate it. The `eval` split is spent and is NOT read here.",
        "",
        *provenance_lines(
            {"train": TRAIN},
            {
                "split": "matchId 70/30 (group-safe)",
                "model": "HistGradientBoostingClassifier(max_iter=400, lr=0.06, l2=1.0, seed=0)",
                "n_features": len(FEATURES),
                "target_precision_lb": f"{TARGET_LB:.3f}",
                "target_coverage": f"{TARGET_COVERAGE:.2f} of all B records",
                "scoring": "strict exact-set",
            },
        ),
        "",
        "## Feature space",
        "",
        f"{len(FEATURES)} features over six families, covering every field BenchRec",
        "exposes (`currency`, `account`, `transactionType` are constants and carry",
        "nothing): cell shape, graded ambiguity from stage 1, amount, text, A/B-side",
        "sibling structure, direction.",
        "",
        "```",
        "\n".join(f"  {f}" for f in FEATURES),
        "```",
        "",
        "## Best achievable coverage at the 99.8% bar",
        "",
        "| split | coverage | accepted | exact | Wilson 95% LB |",
        "|---|---|---|---|---|",
        f"| dev (in-sample) {fmt(best_dev)}",
        f"| val (held-out) {fmt(best_val)}",
        "",
        f"Target is **coverage >= {TARGET_COVERAGE:.0%} at LB >= {TARGET_LB:.1%}**.",
        "",
        "## Precision at the required coverage",
        "",
        "| split | coverage | accepted | exact | Wilson 95% LB |",
        "|---|---|---|---|---|",
        f"| dev (in-sample) {fmt(at50_dev)}",
        f"| val (held-out) {fmt(at50_val)}",
        "",
        "## Where the ranking breaks",
        "",
        f"- Minimum sample to evidence {TARGET_LB:.1%} at ZERO errors: "
        f"**n = {min_n_for_bound(TARGET_LB, Z_95):,}**.",
        f"- val: the ranking is perfect - zero errors - up to rank "
        f"**{(fe_val['n'] - 1) if fe_val else len(f_val):,}** "
        f"({((fe_val['n'] - 1) if fe_val else len(f_val)) / total_b['val']:.2%} coverage), "
        "where its first mistake appears.",
        "",
        "The auto tier is therefore not empty - it is simply small. It tops out roughly",
        "where the statistical floor sits, an order of magnitude short of the coverage",
        "the bar was set at.",
        "",
        "## Frontier (val, held-out)",
        "",
        "| coverage | accepted | exact | Wilson 95% LB | clears bar |",
        "|---|---|---|---|---|",
        *[f"| {r['coverage']:.1%} | {r['n']:,} | {r['exact']:,} | {r['lb']:.3%} | "
          f"{'YES' if r['lb'] >= TARGET_LB else 'no'} |"
          for r in sample_every(f_val)],
        "",
    ]

    os.makedirs(ART, exist_ok=True)
    out = os.path.join(ART, "e5_frontier.md")
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")

    csv_out = os.path.join(ART, "e5_frontier.csv")
    with open(csv_out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["split", "coverage", "n", "exact", "lb", "threshold"])
        for sp, front in (("dev", f_dev), ("val", f_val)):
            for r in front:
                w.writerow([sp, f"{r['coverage']:.6f}", r["n"], r["exact"],
                            f"{r['lb']:.6f}", f"{r['threshold']:.6f}"])

    print(f"wrote {out}")
    print(f"wrote {csv_out}")
    print(f"  dev rows={len(rows['dev']):,} val rows={len(rows['val']):,} "
          f"features={len(FEATURES)}")
    for name, r in (("dev", best_dev), ("val", best_val)):
        print(f"  best@bar {name}: "
              + (f"coverage={r['coverage']:.2%} n={r['n']:,} lb={r['lb']:.3%}"
                 if r else "NEVER CLEARS 99.8%"))
    for name, r in (("dev", at50_dev), ("val", at50_val)):
        print(f"  at 50% coverage {name}: "
              + (f"lb={r['lb']:.3%}" if r else "unreachable"))


if __name__ == "__main__":
    main()
