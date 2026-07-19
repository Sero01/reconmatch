"""Synthetic ledger/statement pairs with known ground truth.

The generator is the only place truth exists; the matching engine never
sees it. Statement-side descriptions are mangled the way banks mangle
them (uppercase, truncation, channel prefixes) so fuzzy matching is
actually exercised.
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel

from reconmatch.schema import Break, LedgerEntry, StatementLine

VENDORS = [
    "Acme Industrial Supplies", "Bharat Office Solutions", "Cloudline Hosting",
    "Deluxe Catering Co", "Eastern Freight Logistics", "Fortune Stationers",
    "Global Talent Payroll", "Hindustan Power & Light", "Iris Marketing Group",
    "Jupiter Telecom", "Kavya Consulting", "Lakshmi Textiles",
    "Metro Property Rentals", "Northline Insurance", "Omega IT Services",
]

_PREFIXES = ["POS ", "NEFT ", "IMPS ", "ACH ", ""]

_BATCH_DESCS = ["BULK PAYMENT", "NEFT BATCH SETTLEMENT", "SALARY BATCH"]


class TruthPair(BaseModel):
    entry_ids: list[str]
    line_ids: list[str]


class Truth(BaseModel):
    pairs: list[TruthPair]
    breaks: list[Break]


def _mangle(rng: random.Random, name: str) -> str:
    out = _PREFIXES[rng.randrange(len(_PREFIXES))] + name.upper()
    return out[:18 + rng.randrange(8)]


def _amount(rng: random.Random) -> Decimal:
    rupees = rng.randint(100, 999_999)
    paise = rng.randint(0, 99)
    sign = -1 if rng.random() < 0.75 else 1  # mostly outflows
    return Decimal(sign * rupees) + Decimal(sign * paise) / 100


def _typo(rng: random.Random, amount: Decimal) -> Decimal:
    """Swap two adjacent digits — the classic keying error."""
    s = f"{abs(amount):.2f}"
    digits = [c for c in s if c.isdigit()]
    if len(digits) < 2:
        return amount + Decimal("1.00")
    i = rng.randrange(len(digits) - 1)
    if digits[i] == digits[i + 1]:
        return amount + Decimal("1.00")
    digits[i], digits[i + 1] = digits[i + 1], digits[i]
    it = iter(digits)
    swapped = "".join(next(it) if c.isdigit() else c for c in s)
    sign = -1 if amount < 0 else 1
    return sign * Decimal(swapped)


def _split(rng: random.Random, amount: Decimal, k: int) -> list[Decimal]:
    """Split amount into k parts that sum exactly."""
    parts = []
    remaining = amount
    for _ in range(k - 1):
        frac = Decimal(rng.randint(20, 60)) / 100
        part = (remaining * frac).quantize(Decimal("0.01"))
        parts.append(part)
        remaining -= part
    parts.append(remaining)
    return parts


def generate_pair(rng: random.Random, n_entries: int = 40,
                  ) -> tuple[list[LedgerEntry], list[StatementLine], Truth]:
    base = date(2026, 3, 2)
    ledger: list[LedgerEntry] = []
    lines: list[StatementLine] = []
    pairs: list[TruthPair] = []
    breaks: list[Break] = []
    line_no = 0
    entry_no = 0

    def new_line(d: date, desc: str, amount: Decimal) -> StatementLine:
        nonlocal line_no
        line_no += 1
        line = StatementLine(line_id=f"S{line_no:04d}", date=d,
                             description=desc, amount=amount)
        lines.append(line)
        return line

    def new_entry(d: date, desc: str, amount: Decimal) -> LedgerEntry:
        nonlocal entry_no
        entry_no += 1
        e = LedgerEntry(entry_id=f"E{entry_no:04d}", date=d,
                        description=desc, amount=amount)
        ledger.append(e)
        return e

    for _ in range(n_entries):
        vendor = VENDORS[rng.randrange(len(VENDORS))]
        d = base + timedelta(days=rng.randrange(28))
        amount = _amount(rng)
        entry = new_entry(d, f"{vendor} invoice {rng.randint(100, 999)}",
                          amount)
        desc = _mangle(rng, vendor)
        roll = rng.random()
        if roll < 0.64:  # clean same-day 1:1
            line = new_line(d, desc, amount)
            pairs.append(TruthPair(entry_ids=[entry.entry_id],
                                   line_ids=[line.line_id]))
        elif roll < 0.70:  # gross batch: this entry + 1-2 more -> one line
            batch = [entry]
            for _ in range(rng.randint(1, 2)):
                v2 = VENDORS[rng.randrange(len(VENDORS))]
                a2 = _amount(rng)
                if (a2 < 0) != (amount < 0):
                    a2 = -a2  # gross batches are same-sign by definition
                batch.append(new_entry(
                    d + timedelta(days=rng.randrange(2)),
                    f"{v2} invoice {rng.randint(100, 999)}", a2))
            total = sum(e.amount for e in batch)
            bline = new_line(d + timedelta(days=rng.randrange(2)),
                             _BATCH_DESCS[rng.randrange(len(_BATCH_DESCS))],
                             total)
            pairs.append(TruthPair(
                entry_ids=[e.entry_id for e in batch],
                line_ids=[bline.line_id]))
        elif roll < 0.80:  # settles 1-3 days later
            line = new_line(d + timedelta(days=rng.randint(1, 3)), desc, amount)
            pairs.append(TruthPair(entry_ids=[entry.entry_id],
                                   line_ids=[line.line_id]))
        elif roll < 0.88:  # split payment
            k = rng.randint(2, 3)
            ids = [new_line(d, desc, part).line_id
                   for part in _split(rng, amount, k)]
            pairs.append(TruthPair(entry_ids=[entry.entry_id], line_ids=ids))
        elif roll < 0.92:  # statement amount keyed wrong
            line = new_line(d, desc, _typo(rng, amount))
            breaks.append(Break(side="ledger", record_id=entry.entry_id,
                                category="amount_mismatch_suspect",
                                suggestion="", related_id=line.line_id))
            breaks.append(Break(side="statement", record_id=line.line_id,
                                category="amount_mismatch_suspect",
                                suggestion="", related_id=entry.entry_id))
        else:  # never hit the bank account
            breaks.append(Break(side="ledger", record_id=entry.entry_id,
                                category="missing_in_statement",
                                suggestion=""))

    for _ in range(2):  # bank fees nobody booked
        fee = -(Decimal(rng.randint(50, 500)) + Decimal(rng.randint(0, 99)) / 100)
        fee_line = new_line(base + timedelta(days=rng.randrange(28)),
                            "BANK CHARGES GST", fee)
        breaks.append(Break(side="statement", record_id=fee_line.line_id,
                            category="missing_in_ledger", suggestion=""))

    if pairs:  # one duplicated statement line
        victim_id = pairs[rng.randrange(len(pairs))].line_ids[0]
        victim = next(line for line in lines if line.line_id == victim_id)
        dup = new_line(victim.date, victim.description, victim.amount)
        breaks.append(Break(side="statement", record_id=dup.line_id,
                            category="duplicate_suspect",
                            related_id=victim.line_id, suggestion=""))

    return ledger, lines, Truth(pairs=pairs, breaks=breaks)


def write_dataset(out_dir: Path, seed: int, n_entries: int = 40) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    ledger, lines, truth = generate_pair(random.Random(seed), n_entries)
    with (out_dir / "ledger.csv").open("w") as f:
        f.write("entry_id,date,description,amount,reference\n")
        for e in ledger:
            f.write(f'{e.entry_id},{e.date},"{e.description}",{e.amount},\n')
    with (out_dir / "statement.csv").open("w") as f:
        f.write("line_id,date,description,amount,reference\n")
        for line in lines:
            f.write(f'{line.line_id},{line.date},"{line.description}",'
                    f"{line.amount},\n")
    (out_dir / "truth.json").write_text(truth.model_dump_json(indent=2))
