"""Scoring reconciliation output against datagen ground truth.

The headline metric is ops-shaped: auto-match rate at a precision floor —
"how much matching work disappears while false matches stay near zero."
Pair precision/recall/F1 and break-classification F1 sit underneath it.
"""
from __future__ import annotations

from reconmatch.datagen import Truth
from reconmatch.schema import Break, MatchPair

BREAK_CATEGORIES = ("missing_in_ledger", "missing_in_statement",
                    "amount_mismatch_suspect", "duplicate_suspect")


def _prf(pred: set, gold: set) -> dict:
    tp = len(pred & gold)
    precision = tp / len(pred) if pred else (1.0 if not gold else 0.0)
    recall = tp / len(gold) if gold else (1.0 if not pred else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def _pair_keys(pairs) -> set:
    return {(p.entry_id, tuple(sorted(p.line_ids))) for p in pairs}


def pair_prf(pred: list[MatchPair], truth: Truth) -> dict:
    """Precision/recall/F1 on (entry_id, sorted line_ids) match pairs."""
    return _prf(_pair_keys(pred), _pair_keys(truth.pairs))


def auto_match_rate(pred: list[MatchPair], truth: Truth,
                    precision_floor: float = 0.99) -> dict:
    """Largest fraction of truth pairs auto-acceptable at precision >= floor.

    Sweeps every confidence threshold present in ``pred``; at each, the
    accepted set is the matches scoring at or above it. Returns the lowest
    threshold whose accepted set both meets the precision floor and recovers
    the most true pairs — the operating point a recon team would ship.
    """
    gold = _pair_keys(truth.pairs)
    n_gold = len(gold)
    # thresholds to try: every distinct confidence, plus one above the max so
    # the empty (vacuously precise, rate 0) accepted set is always a candidate.
    confidences = sorted({m.confidence for m in pred})
    thresholds = confidences + [(confidences[-1] + 1.0) if confidences else 1.0]

    best = {"rate": 0.0, "threshold": 1.0, "precision_at": 1.0}
    for t in thresholds:
        accepted = [(m.entry_id, tuple(sorted(m.line_ids)))
                    for m in pred if m.confidence >= t]
        correct = sum(k in gold for k in accepted)
        precision = correct / len(accepted) if accepted else 1.0
        if precision + 1e-12 < precision_floor:
            continue
        rate = correct / n_gold if n_gold else 0.0
        if rate > best["rate"] or (rate == best["rate"] and t < best["threshold"]):
            best = {"rate": rate, "threshold": float(t), "precision_at": precision}
    return best


def _break_keys(breaks) -> set:
    return {(b.side, b.record_id, b.category) for b in breaks}


def break_prf(pred: list[Break], truth: Truth) -> dict:
    """Micro P/R/F1 on (side, record_id, category), plus a per-category split."""
    pk, gk = _break_keys(pred), _break_keys(truth.breaks)
    out = _prf(pk, gk)
    out["by_category"] = {
        cat: _prf({k for k in pk if k[2] == cat}, {k for k in gk if k[2] == cat})
        for cat in BREAK_CATEGORIES
    }
    return out
