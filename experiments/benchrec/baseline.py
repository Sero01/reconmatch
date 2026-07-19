"""As-is BenchRec baseline for the UNMODIFIED ReconMatch engine.

Faithfulness: we call the engine's own tier functions (_tier1.._tier4) and
reproduce its exact global greedy. The only change is candidate *enumeration*:

  * Tiers 1 & 2 return None unless entry.amount == line.amount, so we only
    ever feed them equal-amount pairs (indexed by Decimal amount). This is
    mathematically identical to the engine's full O(A*B) double loop.
  * Tiers 3 & 4 (subset-sum) internally filter to a +/-date_window, same-sign
    window capped at 12, so we hand each record only its date-windowed
    counterparts -- identical combos, far fewer wasted scans.

Then the same greedy (sort by -confidence, tier, ids; accept if no id reused).
Predictions -> allocation keys -> scored against the public solution.
"""
from __future__ import annotations

import csv
import os
import sys
import time
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(_HERE, "..", "..")
sys.path.insert(0, os.path.join(_ROOT, "src"))

from reconmatch.engine import _tier1, _tier2, _tier3, _tier4, MatchConfig  # noqa: E402
from reconmatch.schema import LedgerEntry, StatementLine                   # noqa: E402

DATA = os.path.join(_ROOT, "data", "benchrec")


def load_eval(path):
    A, B, a_alloc = {}, {}, {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if r["A_id"]:
                A[r["A_id"]] = LedgerEntry(
                    entry_id=r["A_id"],
                    date=date.fromisoformat(r["A_valueDate"]),
                    description=r["A_transactionAttributes"],
                    amount=Decimal(r["A_amount"]),
                    reference=r["A_transactionReferences"] or None)
                a_alloc[r["A_id"]] = (f'{r["A_currencyCode"]}_{r["A_valueDate"]}'
                                      f'_{r["A_account"]}_{r["A_transactionAttributes"]}')
            if r["B_id"]:
                B[r["B_id"]] = StatementLine(
                    line_id=r["B_id"],
                    date=date.fromisoformat(r["B_valueDate"]),
                    description=r["B_transactionAttributes"],
                    amount=Decimal(r["B_amount"]),
                    reference=r["B_transactionReferences"] or None)
    return A, B, a_alloc


def load_solution(path):
    with open(path, newline="") as f:
        return {r["B_id"]: (r["targetAllocation"] or "").strip()
                for r in csv.DictReader(f)}


def windowed(by_day, d, w):
    out = []
    for off in range(-w, w + 1):
        out.extend(by_day.get(d + timedelta(days=off), ()))
    return out


def main():
    t0 = time.time()
    A, B, a_alloc = load_eval(f"{DATA}/BenchRec_cash_v1.0_eval.csv")
    sol = load_solution(f"{DATA}/BenchRec_cash_v1.0_solution.csv")
    print(f"loaded: {len(A)} A, {len(B)} B, {len(sol)} solution", flush=True)
    cfg = MatchConfig()
    w = cfg.date_window_days

    A_by_amt = defaultdict(list)
    A_by_day = defaultdict(list)
    for e in A.values():
        A_by_amt[e.amount].append(e)
        A_by_day[e.date].append(e)
    B_by_day = defaultdict(list)
    for ln in B.values():
        B_by_day[ln.date].append(ln)

    cands = []
    # tiers 1 & 2: equal-amount pairs only (identical to engine's cross product)
    for ln in B.values():
        for e in A_by_amt.get(ln.amount, ()):
            p = _tier1(e, ln, cfg) or _tier2(e, ln, cfg)
            if p:
                cands.append(p)
    print(f"tier1/2 candidates: {len(cands)}  ({time.time() - t0:.0f}s)", flush=True)
    # tier 3: one entry = sum of N lines. Window depends only on the day, so
    # precompute the windowed line-list per day and share it across entries.
    win_lines = {d: windowed(B_by_day, d, w) for d in A_by_day}
    for d, entries in A_by_day.items():
        wl = win_lines[d]
        for e in entries:
            c = _tier3(e, wl, cfg)
            if c:
                cands.extend(c)
    print(f"+tier3  candidates: {len(cands)}  ({time.time() - t0:.0f}s)", flush=True)
    # tier 4: one line = sum of N entries
    win_led = {d: windowed(A_by_day, d, w) for d in B_by_day}
    for d, day_lines in B_by_day.items():
        wl = win_led[d]
        for ln in day_lines:
            c = _tier4(ln, wl, cfg)
            if c:
                cands.extend(c)
    print(f"total candidates: {len(cands)}  ({time.time() - t0:.0f}s)", flush=True)

    # engine's exact global greedy
    cands.sort(key=lambda m: (-m.confidence, m.tier, tuple(m.entry_ids), tuple(m.line_ids)))
    ue, ul = set(), set()
    accepted = []
    for c in cands:
        if ue & set(c.entry_ids) or ul & set(c.line_ids):
            continue
        ue.update(c.entry_ids)
        ul.update(c.line_ids)
        accepted.append(c)

    pred = defaultdict(set)
    tier_pred = defaultdict(int)
    for m in accepted:
        for lid in m.line_ids:
            pred[lid].update(a_alloc[eid] for eid in m.entry_ids)
            tier_pred[m.tier] += 1

    true_has = sum(1 for v in sol.values() if v)
    predicted = correct = 0
    for bid, target in sol.items():
        pset = pred.get(bid)
        if not pset:
            continue
        predicted += 1
        if target and len(pset) == 1 and next(iter(pset)) == target:
            correct += 1
    mr = correct / true_has if true_has else 0
    pr = correct / predicted if predicted else 0
    print("\n==== AS-IS BASELINE (unmodified engine) ====")
    print(f"B transactions: {len(sol)} | with true match: {true_has} | "
          f"true-unmatched: {len(sol) - true_has}")
    print(f"matches accepted: {len(accepted)}  by tier: {dict(sorted(tier_pred.items()))}")
    print(f"engine predicted a match for: {predicted} B's")
    print(f"correct: {correct}")
    print(f"MATCH RATE (recall): {mr * 100:.2f}%")
    print(f"MATCH PRECISION:     {pr * 100:.2f}%   (bar 99.8%)")
    print(f"elapsed {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
