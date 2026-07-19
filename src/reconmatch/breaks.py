"""Classify the unmatched residue after matching, with resolution hints."""
from __future__ import annotations

from reconmatch.engine import MatchConfig, desc_sim, match
from reconmatch.schema import (Break, LedgerEntry, MatchPair, ReconReport,
                               StatementLine)


def _is_transposition(a: str, b: str) -> bool:
    """Same digits, same length, at most two positions differ."""
    da = [c for c in a if c.isdigit()]
    db = [c for c in b if c.isdigit()]
    return (len(da) == len(db) and sorted(da) == sorted(db)
            and sum(x != y for x, y in zip(da, db)) <= 2)


def _near_miss(entry: LedgerEntry, line: StatementLine,
               config: MatchConfig) -> bool:
    if (entry.amount < 0) != (line.amount < 0):
        return False
    if abs((entry.date - line.date).days) > config.date_window_days:
        return False
    if desc_sim(entry.description, line.description) < config.desc_threshold:
        return False
    delta = abs(entry.amount - line.amount)
    tolerance = abs(entry.amount) * config.near_miss_pct
    return delta <= tolerance or _is_transposition(str(entry.amount),
                                                   str(line.amount))


def classify_breaks(ledger: list[LedgerEntry], lines: list[StatementLine],
                    matches: list[MatchPair],
                    config: MatchConfig) -> list[Break]:
    matched_entries = {eid for m in matches for eid in m.entry_ids}
    matched_lines = {i for m in matches for i in m.line_ids}
    open_entries = [e for e in ledger if e.entry_id not in matched_entries]
    open_lines = [s for s in lines if s.line_id not in matched_lines]
    breaks: list[Break] = []

    # 1. near-miss pairs: same story, amounts disagree slightly
    paired_lines: set[str] = set()
    remaining_entries = []
    for entry in open_entries:
        near = next((s for s in open_lines
                     if s.line_id not in paired_lines
                     and _near_miss(entry, s, config)), None)
        if near is None:
            remaining_entries.append(entry)
            continue
        paired_lines.add(near.line_id)
        suggestion = (f"amounts disagree: ledger {entry.amount} vs "
                      f"statement {near.amount} — check for a keying error "
                      f"or an absorbed fee")
        breaks.append(Break(side="ledger", record_id=entry.entry_id,
                            category="amount_mismatch_suspect",
                            suggestion=suggestion, related_id=near.line_id))
        breaks.append(Break(side="statement", record_id=near.line_id,
                            category="amount_mismatch_suspect",
                            suggestion=suggestion, related_id=entry.entry_id))
    open_lines = [s for s in open_lines if s.line_id not in paired_lines]

    # 2. duplicates of already-matched lines
    matched_keys = {}
    for m in matches:
        for lid in m.line_ids:
            line = next(s for s in lines if s.line_id == lid)
            matched_keys[(line.date, line.amount, line.description)] = lid
    still_open = []
    for line in open_lines:
        twin = matched_keys.get((line.date, line.amount, line.description))
        if twin:
            breaks.append(Break(
                side="statement", record_id=line.line_id,
                category="duplicate_suspect", related_id=twin,
                suggestion=f"identical to matched line {twin} — possible "
                           f"double presentation"))
        else:
            still_open.append(line)

    # 3./4. what's left is genuinely one-sided
    for line in still_open:
        breaks.append(Break(
            side="statement", record_id=line.line_id,
            category="missing_in_ledger",
            suggestion=f"no ledger entry for {line.amount} on {line.date} — "
                       f"record it (bank fees and interest are the usual "
                       f"culprits)"))
    for entry in remaining_entries:
        breaks.append(Break(
            side="ledger", record_id=entry.entry_id,
            category="missing_in_statement",
            suggestion=f"ledger expects {entry.amount} around {entry.date} "
                       f"but the bank never saw it — payment may have "
                       f"failed or is still in transit"))
    return breaks


def reconcile(ledger: list[LedgerEntry], lines: list[StatementLine],
              config: MatchConfig = MatchConfig()) -> ReconReport:
    matches = match(ledger, lines, config)
    breaks = classify_breaks(ledger, lines, matches, config)
    n_matched = len({eid for m in matches for eid in m.entry_ids})
    summary = {
        "n_entries": len(ledger),
        "n_lines": len(lines),
        "n_matched_entries": n_matched,
        "match_rate": n_matched / len(ledger) if ledger else 0.0,
        "n_breaks": len(breaks),
    }
    return ReconReport(matches=matches, breaks=breaks, summary=summary)
