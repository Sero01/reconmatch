from datetime import date
from decimal import Decimal

from reconmatch.breaks import classify_breaks, reconcile
from reconmatch.engine import MatchConfig, match
from reconmatch.schema import LedgerEntry, StatementLine


def entry(eid, amount, day=5, desc="Acme Ltd invoice 44"):
    return LedgerEntry(entry_id=eid, date=date(2026, 3, day),
                       description=desc, amount=Decimal(amount))


def line(lid, amount, day=5, desc="POS ACME LTD"):
    return StatementLine(line_id=lid, date=date(2026, 3, day),
                         description=desc, amount=Decimal(amount))


def breaks_for(ledger, lines):
    return classify_breaks(ledger, lines, match(ledger, lines), MatchConfig())


def test_amount_mismatch_suspect_links_both_sides():
    ledger = [entry("E1", "-1250.50")]
    lines = [line("S1", "-1250.05")]  # transposed final digits
    bks = breaks_for(ledger, lines)
    ledger_break = next(b for b in bks if b.side == "ledger")
    assert ledger_break.category == "amount_mismatch_suspect"
    assert ledger_break.related_id == "S1"
    assert "-1250.50" in ledger_break.suggestion
    assert "-1250.05" in ledger_break.suggestion


def test_duplicate_statement_line_flagged():
    ledger = [entry("E1", "-99.00")]
    lines = [line("S1", "-99.00"), line("S2", "-99.00")]
    bks = breaks_for(ledger, lines)
    [dup] = [b for b in bks if b.category == "duplicate_suspect"]
    assert dup.side == "statement"
    assert dup.related_id in {"S1", "S2"}


def test_unmatched_fee_is_missing_in_ledger():
    bks = breaks_for([], [line("S1", "-118.00", desc="BANK CHARGES GST")])
    assert bks[0].category == "missing_in_ledger"
    assert bks[0].side == "statement"


def test_unmatched_entry_is_missing_in_statement():
    bks = breaks_for([entry("E1", "-500.00")], [])
    assert bks[0].category == "missing_in_statement"
    assert bks[0].side == "ledger"


def test_reconcile_summary_counts():
    ledger = [entry("E1", "-100.00"), entry("E2", "-200.00")]
    lines = [line("S1", "-100.00")]
    report = reconcile(ledger, lines)
    assert report.summary["n_entries"] == 2
    assert report.summary["n_matched_entries"] == 1
    assert report.summary["match_rate"] == 0.5
    assert report.summary["n_breaks"] == len(report.breaks)
