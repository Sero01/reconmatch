from datetime import date
from decimal import Decimal

import pytest

from reconmatch.schema import (Break, MatchPair, ReconReport,
                               RowError, load_ledger_csv,
                               load_statement_csv)


def test_ledger_csv_round_trip(tmp_path):
    p = tmp_path / "l.csv"
    p.write_text("entry_id,date,description,amount\n"
                 "E1,2026-01-05,VENDOR PAYMENT,-1250.50\n")
    [e] = load_ledger_csv(p)
    assert e.amount == Decimal("-1250.50")
    assert e.date == date(2026, 1, 5)
    assert e.reference is None


def test_statement_csv_with_reference(tmp_path):
    p = tmp_path / "s.csv"
    p.write_text("line_id,date,description,amount,reference\n"
                 "S1,2026-01-06,POS ACME,-99.99,INV-44\n")
    [line] = load_statement_csv(p)
    assert line.reference == "INV-44"
    assert line.amount == Decimal("-99.99")


def test_malformed_row_reports_row_number(tmp_path):
    p = tmp_path / "l.csv"
    p.write_text("entry_id,date,description,amount\n"
                 "E1,notadate,X,1.0\n")
    with pytest.raises(RowError) as ei:
        load_ledger_csv(p)
    assert ei.value.row == 2


def test_missing_column_reports_clearly(tmp_path):
    p = tmp_path / "l.csv"
    p.write_text("entry_id,description,amount\nE1,X,1.0\n")
    with pytest.raises(RowError) as ei:
        load_ledger_csv(p)
    assert "date" in str(ei.value)


def test_models_construct():
    m = MatchPair(entry_id="E1", line_ids=["S1", "S2"], tier=3, confidence=0.61)
    b = Break(side="statement", record_id="S9", category="missing_in_ledger",
              suggestion="record this statement line in the ledger")
    r = ReconReport(matches=[m], breaks=[b], summary={"match_rate": 0.9})
    assert r.matches[0].tier == 3
    assert r.breaks[0].related_id is None
