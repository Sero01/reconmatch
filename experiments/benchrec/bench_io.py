"""Shared BenchRec loaders for the E0-E3 experiment harness.

Kept separate from ``baseline.py`` (which stays a pristine record of the
as-is engine result) and from ``src/reconmatch/`` (the production package is
untouched until a validated path is folded in under its own gate).

Schema facts established in E0 (see profile.py / e0_profile.md):
  * Train rows are single-sided: each row carries EITHER an A record or a B
    record, grouped into a match by ``matchId``. Ground-truth cardinality
    (1:1, 1:N, N:1, N:M) is recovered by grouping on ``matchId``.
  * Amounts are stored as unsigned magnitudes; direction lives in
    ``debitOrCredit`` (DR/CR). True matches are OPPOSITE direction, so the
    match key is the unsigned magnitude, not a signed amount.
  * A_allocation == ``{currency}_{valueDate}_{account}_{attributes}`` for
    100% of A rows, so a predicted A reconstructs its target allocation exactly.
"""
from __future__ import annotations

import csv
import hashlib
import os
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Record:
    """One side (A or B) of a BenchRec row, normalized for matching."""
    rec_id: str
    side: str           # "A" or "B"
    minor: int          # unsigned amount in minor units (cents)
    value_date: str     # ISO date string, used verbatim as a block key
    direction: str      # "DR" or "CR"
    reference: str      # raw transactionReferences ("" when absent)
    attributes: str     # raw transactionAttributes (char-obfuscated narrative)
    currency: str
    account: str
    allocation: str     # A_allocation (A side) or "" (B side)
    target: str         # targetAllocation (B side) or "" (A side)


def to_minor(amount: str) -> int:
    """Unsigned amount magnitude in minor units. Empty -> 0 (A/B-absent side)."""
    if not amount:
        return 0
    return int((Decimal(amount) * 100).to_integral_value())


def reconstruct_alloc(cur: str, value_date: str, account: str, attributes: str) -> str:
    return f"{cur}_{value_date}_{account}_{attributes}"


def _a_record(row: dict) -> Record:
    return Record(
        rec_id=row["A_id"], side="A", minor=to_minor(row["A_amount"]),
        value_date=row["A_valueDate"], direction=row["A_debitOrCredit"],
        reference=row["A_transactionReferences"], attributes=row["A_transactionAttributes"],
        currency=row["A_currencyCode"], account=row["A_account"],
        allocation=row["A_allocation"], target="")


def _b_record(row: dict) -> Record:
    return Record(
        rec_id=row["B_id"], side="B", minor=to_minor(row["B_amount"]),
        value_date=row["B_valueDate"], direction=row["B_debitOrCredit"],
        reference=row["B_transactionReferences"], attributes=row["B_transactionAttributes"],
        currency=row["B_currencyCode"], account=row["B_account"],
        allocation="", target=row["targetAllocation"])


def load_train(path: str):
    """Return (a_records, b_records, groups).

    ``groups`` maps matchId -> {"A": [Record...], "B": [Record...]}, the
    ground-truth match structure. A/B lists are the full per-side populations.
    """
    a_records: list[Record] = []
    b_records: list[Record] = []
    groups: dict[str, dict[str, list[Record]]] = defaultdict(lambda: {"A": [], "B": []})
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if row["A_id"]:
                rec = _a_record(row)
                a_records.append(rec)
                groups[row["matchId"]]["A"].append(rec)
            if row["B_id"]:
                rec = _b_record(row)
                b_records.append(rec)
                groups[row["matchId"]]["B"].append(rec)
    return a_records, b_records, groups


def load_eval(path: str):
    """Return (a_records, b_records) for the eval split (no truth here)."""
    a_records: list[Record] = []
    b_records: list[Record] = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if row["A_id"]:
                a_records.append(_a_record(row))
            if row["B_id"]:
                b_records.append(_b_record(row))
    return a_records, b_records


def load_solution(path: str) -> dict[str, str]:
    """Return B_id -> targetAllocation (stripped; "" means true-unmatched)."""
    with open(path, newline="") as f:
        return {r["B_id"]: (r["targetAllocation"] or "").strip()
                for r in csv.DictReader(f)}


# --- Run provenance (research: checksum + schema + config + code version) -------

def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_sha() -> str:
    try:
        root = os.path.join(os.path.dirname(__file__), "..", "..")
        out = subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5)
        sha = out.stdout.strip()
        dirty = subprocess.run(["git", "-C", root, "status", "--porcelain"],
                               capture_output=True, text=True, timeout=5).stdout.strip()
        return f"{sha}{'-dirty' if dirty else ''}" if sha else "unknown"
    except Exception:
        return "unknown"


def provenance_lines(datasets: dict[str, str], config: dict) -> list[str]:
    """Markdown provenance block: dataset SHA-256s, git code version, config, UTC time.

    ``datasets`` maps a label -> file path; ``config`` is any run parameters
    (split seed, feature schema, thresholds) worth pinning for reproducibility.
    """
    lines = ["<!-- provenance -->", "## Run provenance",
             f"- generated (UTC): {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
             f"- code (git): `{git_sha()}`"]
    for label, path in datasets.items():
        sha = file_sha256(path) if os.path.exists(path) else "MISSING"
        lines.append(f"- {label}: `{os.path.basename(path)}` sha256 `{sha[:16]}…`")
    for k, v in config.items():
        lines.append(f"- {k}: `{v}`")
    return lines
