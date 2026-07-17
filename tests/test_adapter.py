import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from reconmatch.adapter import statement_lines_from_docval

FIXTURE = Path(__file__).parent / "fixtures" / "docval_sample.json"


def _lines():
    return statement_lines_from_docval(json.loads(FIXTURE.read_text()))


def test_row_count_matches_transactions():
    data = json.loads(FIXTURE.read_text())
    assert len(_lines()) == len(data["doc"]["transactions"])


def test_debit_row_is_negative_decimal():
    line = _lines()[0]  # row 0 is a debit
    assert line.amount == Decimal("-20544.01")
    assert isinstance(line.amount, Decimal)
    assert line.date == date(2026, 1, 3)
    assert line.line_id == "T0000"


def test_credit_row_is_positive():
    line = _lines()[5]  # row 5 is a credit
    assert line.amount == Decimal("13394.19")
