"""E5 stage 1 - is the group partition identifiable from the observables?

Every earlier experiment asked "can I find a feature that separates correct
predictions from wrong ones?". This module asks the prior question: **is the
answer a function of the input at all?**

At eval time the observable data is, per record, ``currency``, ``account``,
``valueDate``, ``amount``, ``direction``, ``transactionReferences`` and
``transactionAttributes``. On BenchRec ``currency``, ``account`` and
``transactionType`` are constants, so the whole observable space is amount, date,
direction and two char-obfuscated text fields. The label - the partition of
records into ``matchId`` groups - is never observable.

A *legal partition* is one where every group has a non-empty A side and B side of
opposite direction and balances (``sum(A amounts) == sum(B amounts)``). The
dataset's true partition is legal; so are others.

An *ambiguity witness* for a cell C is another legal partition of the same date's
records under which C's B records belong to a strictly larger group. The minimal
construction is direct: if C is balanced and some other balanced cell C' sits on
the same date, then ``C u C'`` is itself a legal group. C alone and ``C u C'``
are both perfectly consistent with every observable, yet they imply *different*
correct answers for every B in C.

Where a witness exists no function of the observables can decide the case, since
two different correct answers share one input. That is an impossibility result
rather than a failed search, and it does not depend on which features were tried.

The same computation is constructive. Cells with NO witness are provably
unambiguous given the observables, so they are the principled auto-tier
candidates - safe by construction rather than by a fitted threshold. This module
scores that witness-free tier against the stated floor:

    precision Wilson 95% LB >= 99.8%  AND  coverage >= 50% of all B records

Selection is on dev, confirmation on val. `eval` is spent and is never read here.

Run:  uv run python experiments/benchrec/identifiability.py
Emits: data/benchrec/artifacts/e5_identifiability.md
       data/benchrec/artifacts/e5_witnesses.csv
"""
from __future__ import annotations

import csv
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)

from bench_io import load_train, provenance_lines           # noqa: E402
from bench_stats import Z_95, wilson_lower_bound            # noqa: E402
from groups import (                                         # noqa: E402
    EXACT,
    build_components,
    classify,
    population,
    predict,
    split_groups,
    truth_maps,
)

DATA = os.path.join(HERE, "..", "..", "data", "benchrec")
TRAIN = os.path.join(DATA, "BenchRec_cash_v1.0_train.csv")
ART = os.path.join(DATA, "artifacts")

SPLITS = ("dev", "val")

# The falsifiable target, fixed before the run (see the design spec).
TARGET_LB = 0.998
TARGET_COVERAGE = 0.50

# Witness levels.
L1 = "L1_balance"          # merge is balanced -> legal
L2 = "L2_balance_token"    # legal AND the merged A side shares a token, so a
                           # text-aware method could not reject it either
NONE = "none"


def date_key(key: tuple) -> tuple:
    """The (currency, account, value_date) a cell sits in."""
    return key[:3]


def amount_of(key: tuple) -> int:
    return key[3]


def tokens(rec) -> frozenset[str]:
    """Whitespace tokens of a record's text fields, casefolded."""
    return frozenset(f"{rec.attributes} {rec.reference}".casefold().split())


def imbalance(key: tuple, cell) -> int:
    """``sum(A) - sum(B)`` for a cell. Every record in a cell shares one amount,
    so this is the count difference scaled by that amount."""
    return (len(cell["A"]) - len(cell["B"])) * amount_of(key)


def is_balanced(key: tuple, cell) -> bool:
    return imbalance(key, cell) == 0 and bool(cell["A"]) and bool(cell["B"])


def a_tokens_common(cells) -> frozenset[str]:
    """Tokens shared by EVERY A record across the given cells."""
    common: frozenset[str] | None = None
    for cell in cells:
        for a in cell["A"]:
            t = tokens(a)
            common = t if common is None else (common & t)
            if not common:
                return frozenset()
    return common or frozenset()


def witness_for(key, cell, by_date):
    """Strongest ambiguity witness for ``cell``, or NONE.

    Searched constructions, in order of strength:

    1. **Another balanced cell on the same date.** ``C u C'`` balances, both
       sides non-empty -> a legal group strictly containing C. This is the
       dominant case and the one the true multi-amount groups actually look like.
    2. **Two other cells whose imbalances cancel.** ``C u C1 u C2`` balances when
       ``imb(C1) == -imb(C2)``, covering merges that pull in A-only or B-only
       cells.

    Reported as L2 when the level-1 merge also leaves the combined A side sharing
    a token - the regularity a text-aware method could otherwise exploit to
    reject the merge - and L1 when it is merely legal. Returning NONE means no
    witness of either construction exists, not that none can: three-way
    imbalance cancellations are not searched. The tier built from NONE cells is
    therefore an OPTIMISTIC upper bound on what is provably safe, which is the
    honest direction for a claim we are trying to disprove.
    """
    siblings = [(k, c) for k, c in by_date[date_key(key)].items() if k != key]
    if not siblings:
        return NONE, None

    for k, c in siblings:
        if is_balanced(k, c):
            if a_tokens_common([cell, c]):
                return L2, k
            return L1, k

    seen: dict[int, tuple] = {}
    for k, c in siblings:
        imb = imbalance(k, c)
        if -imb in seen:
            return L1, k
        seen[imb] = k
    return NONE, None


def analyse(pop, b_target):
    """One row per B record that receives a prediction, with its witness level."""
    cells = build_components(pop)
    by_date: dict[tuple, dict] = defaultdict(dict)
    for key, cell in cells.items():
        by_date[date_key(key)][key] = cell

    rows = []
    for key, cell in cells.items():
        if not cell["B"]:
            continue
        predicted = predict(cell)
        level, via = witness_for(key, cell, by_date)
        for b in cell["B"]:
            target = b_target.get(b.rec_id, frozenset())
            rows.append({
                "b_id": b.rec_id,
                "value_date": key[2],
                "amount_minor": key[3],
                "shape": f"({len(cell['A'])},{len(cell['B'])})",
                "emitted": bool(predicted),
                "outcome": classify(predicted, target),
                "witness": level,
                "witness_via_amount": amount_of(via) if via else "",
                "date_cells": len(by_date[date_key(key)]),
            })
    return rows


def tier_stats(rows, predicate):
    """(coverage_n, emitted, exact, lb) for the sub-tier selected by predicate."""
    sel = [r for r in rows if predicate(r)]
    emitted = [r for r in sel if r["emitted"]]
    exact = sum(1 for r in emitted if r["outcome"] == EXACT)
    lb = wilson_lower_bound(exact, len(emitted), Z_95)
    return len(sel), len(emitted), exact, lb


def main() -> None:
    _a, _b, groups = load_train(TRAIN)
    b_target, b_card, _b_amount = truth_maps(groups)
    per_split = split_groups(groups)

    rows_by_split = {}
    total_b = {}
    for sp in SPLITS:
        pop = population(per_split[sp])
        total_b[sp] = len(pop["B"])
        rows_by_split[sp] = analyse(pop, b_target)

    lines = [
        "# E5 stage 1 - identifiability of the group partition",
        "",
        "> Generated by `experiments/benchrec/identifiability.py`. Group-safe train",
        "> dev/val split; strict exact-set outcomes; Wilson 95% one-sided LB.",
        "> The `eval` split is spent and is NOT read by this module.",
        "",
        *provenance_lines(
            {"train": TRAIN},
            {
                "split": "matchId 70/30 (group-safe)",
                "target_precision_lb": f"{TARGET_LB:.3f}",
                "target_coverage": f"{TARGET_COVERAGE:.2f} of all B records",
                "witness_levels": "L1 balance-only, L2 balance + A-side shared token",
                "scoring": "strict exact-set",
            },
        ),
        "",
        "## The question",
        "",
        "`matchId` is not an eval-time input, so the group partition is a *hidden*",
        "variable. A cell holding one A and one B at the same amount is a legal 1:1",
        "group by itself; if another balanced cell sits on the same date, merging the",
        "two is an equally legal 2:2 multi-amount group. Both are consistent with every",
        "observable, and they disagree about the correct answer for the cell's B's.",
        "Where such a witness exists, no feature can decide the case - two different",
        "correct answers share one input.",
        "",
    ]

    for sp in SPLITS:
        rows = rows_by_split[sp]
        counts = Counter(r["witness"] for r in rows)
        err = [r for r in rows if r["emitted"] and r["outcome"] != EXACT]
        err_counts = Counter(r["witness"] for r in err)

        lines += [
            f"## {sp} - witness prevalence",
            "",
            f"- B records receiving a prediction path: **{len(rows):,}** "
            f"(of {total_b[sp]:,} B's in the split)",
            f"- errors among emitted predictions: **{len(err):,}**",
            "",
            "| witness level | B records | share | errors | error share |",
            "|---|---|---|---|---|",
        ]
        for lvl in (L2, L1, NONE):
            n = counts.get(lvl, 0)
            e = err_counts.get(lvl, 0)
            lines.append(
                f"| {lvl} | {n:,} | {n / max(1, len(rows)):.2%} | {e:,} | "
                f"{e / max(1, len(err)):.2%} |"
            )
        lines.append("")

        # The constructive half: the witness-free tier, scored against the floor.
        cov_n, emitted, exact, lb = tier_stats(rows, lambda r: r["witness"] == NONE)
        coverage = cov_n / max(1, total_b[sp])
        passes = lb >= TARGET_LB and coverage >= TARGET_COVERAGE
        lines += [
            f"### {sp} - auto tier from witness-free cells",
            "",
            "| quantity | value | target | meets |",
            "|---|---|---|---|",
            f"| coverage | {cov_n:,} B's = {coverage:.2%} | >= {TARGET_COVERAGE:.0%} | "
            f"{'YES' if coverage >= TARGET_COVERAGE else 'NO'} |",
            f"| emitted | {emitted:,} | - | - |",
            f"| exact | {exact:,} | - | - |",
            f"| precision Wilson 95% LB | {lb:.2%} | >= {TARGET_LB:.1%} | "
            f"{'YES' if lb >= TARGET_LB else 'NO'} |",
            "",
            f"**{sp} verdict: {'AUTO BAR MET' if passes else 'AUTO BAR NOT MET'}**",
            "",
        ]

        # Contrast: error rate inside vs outside the ambiguous population. If these
        # are equal the witness carries no information and neither can any feature.
        amb_n, amb_em, amb_ex, _ = tier_stats(rows, lambda r: r["witness"] != NONE)
        amb_err = amb_em - amb_ex
        free_err = emitted - exact
        lines += [
            "| population | emitted | errors | error rate |",
            "|---|---|---|---|",
            f"| has a witness (undecidable) | {amb_em:,} | {amb_err:,} | "
            f"{amb_err / max(1, amb_em):.3%} |",
            f"| witness-free (decidable) | {emitted:,} | {free_err:,} | "
            f"{free_err / max(1, emitted):.3%} |",
            "",
        ]

    out = os.path.join(ART, "e5_identifiability.md")
    os.makedirs(ART, exist_ok=True)
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")

    csv_out = os.path.join(ART, "e5_witnesses.csv")
    with open(csv_out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_by_split["dev"][0]) + ["split"])
        w.writeheader()
        for sp in SPLITS:
            for r in rows_by_split[sp]:
                w.writerow({**r, "split": sp})

    print(f"wrote {out}")
    print(f"wrote {csv_out}")
    for sp in SPLITS:
        rows = rows_by_split[sp]
        c = Counter(r["witness"] for r in rows)
        print(f"  {sp}: witness-free={c.get(NONE, 0):,} "
              f"L1={c.get(L1, 0):,} L2={c.get(L2, 0):,} of {len(rows):,}")


if __name__ == "__main__":
    main()
