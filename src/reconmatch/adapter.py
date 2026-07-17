"""Bridge DocVal extraction JSON into ReconMatch statement lines.

Lets a bank statement flow extraction -> validation (DocVal) -> reconciliation
(ReconMatch) end to end. Deliberately no import of the docval package: this
reads the on-the-wire JSON shape and produces ReconMatch's own schema, so the
two repos stay decoupled.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from reconmatch.schema import StatementLine


def statement_lines_from_docval(extraction_json: dict) -> list[StatementLine]:
    """Map a DocVal StatementDoc result into signed statement lines.

    Amount convention matches the rest of ReconMatch: credit − debit, so money
    into the account is positive and money out is negative.
    """
    lines: list[StatementLine] = []
    for i, txn in enumerate(extraction_json["doc"]["transactions"]):
        credit = Decimal(txn["credit"]) if txn.get("credit") else Decimal(0)
        debit = Decimal(txn["debit"]) if txn.get("debit") else Decimal(0)
        lines.append(StatementLine(
            line_id=f"T{i:04d}",
            date=date.fromisoformat(txn["txn_date"]),
            description=txn["description"],
            amount=credit - debit,
            reference=None,
        ))
    return lines
