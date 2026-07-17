"""Data contracts: ledger/statement records, matches, breaks, report.

All money is Decimal, all dates are datetime.date. Amounts are signed:
positive = money into the bank account, negative = money out.
"""
from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

BreakCategory = Literal["missing_in_ledger", "missing_in_statement",
                        "amount_mismatch_suspect", "duplicate_suspect"]


class LedgerEntry(BaseModel):
    entry_id: str
    date: date
    description: str
    amount: Decimal
    reference: str | None = None


class StatementLine(BaseModel):
    line_id: str
    date: date
    description: str
    amount: Decimal
    reference: str | None = None


class MatchPair(BaseModel):
    entry_id: str
    line_ids: list[str]
    tier: int
    confidence: float


class Break(BaseModel):
    side: Literal["ledger", "statement"]
    record_id: str
    category: BreakCategory
    suggestion: str
    related_id: str | None = None


class ReconReport(BaseModel):
    matches: list[MatchPair]
    breaks: list[Break]
    summary: dict[str, float | int]


class RowError(Exception):
    """A CSV row that cannot be parsed; carries its 1-based row number."""

    def __init__(self, row: int, message: str):
        super().__init__(f"row {row}: {message}")
        self.row = row


def _load_csv(path: Path, id_column: str) -> list[dict]:
    records = []
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        for i, raw in enumerate(reader, start=2):  # row 1 is the header
            try:
                records.append({
                    id_column: raw[id_column],
                    "date": date.fromisoformat(raw["date"].strip()),
                    "description": raw["description"],
                    "amount": Decimal(raw["amount"].strip()),
                    "reference": raw.get("reference") or None,
                })
            except KeyError as e:
                raise RowError(i, f"missing column {e.args[0]}") from e
            except (ValueError, InvalidOperation) as e:
                raise RowError(i, str(e)) from e
    return records


def load_ledger_csv(path: Path) -> list[LedgerEntry]:
    return [LedgerEntry(**r) for r in _load_csv(path, "entry_id")]


def load_statement_csv(path: Path) -> list[StatementLine]:
    return [StatementLine(**r) for r in _load_csv(path, "line_id")]
