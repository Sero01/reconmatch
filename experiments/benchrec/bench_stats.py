"""Statistical + partitioning helpers for the BenchRec experiment ladder.

Three concerns the reviewer flagged:
  * group-safe dev/validation split (never split a matchId across partitions,
    so a design choice validated on `val` has not seen any of its group's rows);
  * a Wilson one-sided lower confidence bound on precision, so a small sample
    with few observed errors cannot be reported as meeting the 99.8% bar;
  * cardinality stratification, so 1:1 performance is never conflated with the
    N:M groups the 1:1 path cannot resolve.
"""
from __future__ import annotations

import hashlib
import math

# One-sided normal quantiles. z=1.645 -> 95%, z=2.326 -> 99%.
Z_95 = 1.645
Z_99 = 2.326


def wilson_lower_bound(k: int, n: int, z: float = Z_95) -> float:
    """One-sided Wilson lower bound on a binomial proportion k/n."""
    if n == 0:
        return 0.0
    p = k / n
    denom = 1 + z * z / n
    center = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (center - margin) / denom


def min_n_for_bound(target: float = 0.998, z: float = Z_95) -> int:
    """Smallest n with ZERO observed errors whose Wilson lower bound >= target.

    States the minimum accepted-match sample size below which a perfect
    observation still cannot evidence the target precision.
    """
    n = 1
    while wilson_lower_bound(n, n, z) < target:
        n += 1
        if n > 10_000_000:
            break
    return n


def cardinality_class(n_a: int, n_b: int) -> str:
    """Group cardinality from a B record's perspective (A=ledger, B=statement)."""
    if n_b == 0:
        return "A-only"
    if n_a == 0:
        return "unmatched"      # B with no ledger partner (true-unmatched)
    if n_a == 1 and n_b == 1:
        return "1:1"
    if n_a == 1 and n_b > 1:
        return "1:N"            # one ledger entry, many statement lines
    if n_a > 1 and n_b == 1:
        return "N:1"            # batch: many ledger entries, one statement line
    return "N:M"


def assign_split(match_id: str, dev_frac: float = 0.7) -> str:
    """Deterministic group-safe split. Same matchId -> same partition always."""
    h = int(hashlib.sha1(match_id.encode()).hexdigest(), 16)
    return "dev" if (h % 10_000) < dev_frac * 10_000 else "val"


def split_populations(groups, dev_frac: float = 0.7):
    """Partition groups into dev/val populations, group-safe.

    Returns (pops, b_card) where pops[split] = {"A": [...], "B": [...]} and
    b_card maps each B rec_id -> its group's cardinality class.
    """
    pops = {"dev": {"A": [], "B": []}, "val": {"A": [], "B": []}}
    b_card: dict[str, str] = {}
    for match_id, g in groups.items():
        split = assign_split(match_id, dev_frac)
        cls = cardinality_class(len(g["A"]), len(g["B"]))
        pops[split]["A"].extend(g["A"])
        pops[split]["B"].extend(g["B"])
        for b in g["B"]:
            b_card[b.rec_id] = cls
    return pops, b_card


# --- Candidate eligibility (research: mandatory hard-scope partitioning) --------
# Scope partitions on fields that must be INVARIANT for a match (currency,
# account). Direction is a RELATIONAL constraint (a match is opposite DR/CR, per
# E0) so it is applied as a filter, not folded into the equality key. On BenchRec
# currency/account are constant and blocks are single-direction, so both are
# no-ops on the numbers - but they are encoded for correctness and to generalize
# to multi-currency / mixed-direction data, as the research requires.

def scope_key(rec) -> tuple:
    """Hard-scope equality key: amount magnitude, value date, currency, account."""
    return (rec.minor, rec.value_date, rec.currency, rec.account)


def build_scope_index(records) -> dict:
    index: dict[tuple, list] = {}
    for r in records:
        index.setdefault(scope_key(r), []).append(r)
    return index


def eligible_candidates(b, a_index: dict) -> list:
    """A records in B's scope whose direction is opposite (a valid match)."""
    return [a for a in a_index.get(scope_key(b), []) if a.direction != b.direction]
