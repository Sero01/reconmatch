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
from __future__ import annotations

from decimal import Decimal
from difflib import SequenceMatcher
from itertools import combinations

from pydantic import BaseModel

from reconmatch.schema import LedgerEntry, MatchPair, StatementLine


class MatchConfig(BaseModel):
    date_window_days: int = 3
    desc_threshold: float = 0.55
    max_split: int = 3
    near_miss_pct: Decimal = Decimal("0.01")


def desc_sim(a: str, b: str) -> float:
    """Char-level ratio or token containment, whichever is stronger.

    Banks mangle payee names (channel prefixes, uppercase, truncation), so
    "Acme Ltd invoice 44" must still find "POS ACME LTD": token containment
    catches shared words; the char ratio catches truncated single tokens.
    """
    a, b = a.casefold(), b.casefold()
    char = SequenceMatcher(None, a, b).ratio()
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return char
    containment = len(ta & tb) / min(len(ta), len(tb))
    return max(char, containment)


def _tier1(entry: LedgerEntry, line: StatementLine,
           config: MatchConfig) -> MatchPair | None:
    if entry.amount != line.amount or entry.date != line.date:
        return None
    if entry.reference is not None and entry.reference == line.reference:
        return MatchPair(entry_ids=[entry.entry_id], line_ids=[line.line_id],
                         tier=1, confidence=1.0)
    if desc_sim(entry.description, line.description) >= config.desc_threshold:
        return MatchPair(entry_ids=[entry.entry_id], line_ids=[line.line_id],
                         tier=1, confidence=0.95)
    return None


def _tier2(entry: LedgerEntry, line: StatementLine,
           config: MatchConfig) -> MatchPair | None:
    gap = abs((entry.date - line.date).days)
    if entry.amount != line.amount or not 0 < gap <= config.date_window_days:
        return None
    sim = desc_sim(entry.description, line.description)
    if sim < config.desc_threshold:
        return None
    confidence = 0.6 + 0.3 * sim * (1 - gap / (config.date_window_days + 1))
    return MatchPair(entry_ids=[entry.entry_id], line_ids=[line.line_id],
                     tier=2, confidence=confidence)


def _tier3(entry: LedgerEntry, lines: list[StatementLine],
           config: MatchConfig) -> list[MatchPair]:
    window = [
        line for line in lines
        if abs((entry.date - line.date).days) <= config.date_window_days
        and (line.amount < 0) == (entry.amount < 0)
    ][:12]  # bound the combination search
    out = []
    for k in range(2, config.max_split + 1):
        for combo in combinations(window, k):
            if sum(c.amount for c in combo) != entry.amount:
                continue
            sims = [desc_sim(entry.description, c.description) for c in combo]
            confidence = 0.55 + 0.15 * (sum(sims) / len(sims)) - 0.05 * (k - 2)
            out.append(MatchPair(
                entry_ids=[entry.entry_id],
                line_ids=sorted(c.line_id for c in combo),
                tier=3, confidence=confidence))
    return out


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


def match(ledger: list[LedgerEntry], lines: list[StatementLine],
          config: MatchConfig = MatchConfig()) -> list[MatchPair]:
    ledger = sorted(ledger, key=lambda e: e.entry_id)
    lines = sorted(lines, key=lambda s: s.line_id)
    candidates: list[MatchPair] = []
    for entry in ledger:
        for line in lines:
            for tier in (_tier1, _tier2):
                pair = tier(entry, line, config)
                if pair:
                    candidates.append(pair)
        candidates.extend(_tier3(entry, lines, config))
    for line in lines:
        candidates.extend(_tier4(line, ledger, config))

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
