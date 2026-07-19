from reconmatch.datagen import Truth, TruthPair
from reconmatch.schema import Break, MatchPair

from eval.metrics import auto_match_rate, break_prf, pair_prf


def _truth():
    return Truth(
        pairs=[
            TruthPair(entry_ids=["E1"], line_ids=["S1"]),
            TruthPair(entry_ids=["E2"], line_ids=["S2", "S3"]),
        ],
        breaks=[],
    )


def _pair(entry_id, line_ids, confidence, tier=1):
    return MatchPair(entry_ids=[entry_id], line_ids=line_ids, tier=tier,
                     confidence=confidence)


def test_pair_prf_perfect():
    pred = [_pair("E1", ["S1"], 0.95), _pair("E2", ["S3", "S2"], 0.60, tier=3)]
    m = pair_prf(pred, _truth())
    assert m["precision"] == 1.0 and m["recall"] == 1.0 and m["f1"] == 1.0


def test_pair_prf_partial():
    pred = [_pair("E1", ["S1"], 0.95), _pair("E9", ["S9"], 0.80)]
    m = pair_prf(pred, _truth())
    assert m["precision"] == 0.5  # one of two predicted is correct
    assert m["recall"] == 0.5     # one of two gold recovered


def test_auto_match_rate_perfect():
    pred = [_pair("E1", ["S1"], 0.95), _pair("E2", ["S2", "S3"], 0.60, tier=3)]
    r = auto_match_rate(pred, _truth(), precision_floor=0.99)
    assert r["rate"] == 1.0 and r["precision_at"] >= 0.99


def test_false_match_caps_rate_below_one():
    # E1 (0.95, correct), E9 (0.80, WRONG), E2 (0.60, correct).
    # Admitting E2 forces the threshold down past the wrong E9 match,
    # so at a 0.99 precision floor E2 can never be auto-accepted.
    pred = [
        _pair("E1", ["S1"], 0.95),
        _pair("E9", ["S9"], 0.80, tier=2),
        _pair("E2", ["S2", "S3"], 0.60, tier=3),
    ]
    r = auto_match_rate(pred, _truth(), precision_floor=0.99)
    assert 0.0 < r["rate"] < 1.0
    assert r["precision_at"] >= 0.99


def test_returned_threshold_actually_achieves_floor():
    pred = [
        _pair("E1", ["S1"], 0.95),
        _pair("E9", ["S9"], 0.80, tier=2),
        _pair("E2", ["S2", "S3"], 0.60, tier=3),
    ]
    truth = _truth()
    r = auto_match_rate(pred, truth, precision_floor=0.99)
    gold = {(tuple(sorted(p.entry_ids)), tuple(sorted(p.line_ids)))
            for p in truth.pairs}
    accepted = [m for m in pred if m.confidence >= r["threshold"]]
    correct = sum((tuple(sorted(m.entry_ids)), tuple(sorted(m.line_ids))) in gold
                  for m in accepted)
    precision = correct / len(accepted) if accepted else 1.0
    assert precision >= 0.99


def test_break_prf_perfect():
    b = Break(side="statement", record_id="S5",
              category="missing_in_ledger", suggestion="x")
    m = break_prf([b], Truth(pairs=[], breaks=[b]))
    assert m["f1"] == 1.0
    assert m["by_category"]["missing_in_ledger"]["f1"] == 1.0


def test_break_prf_wrong_category_scored_as_miss():
    gold = Break(side="statement", record_id="S5",
                 category="missing_in_ledger", suggestion="")
    pred = Break(side="statement", record_id="S5",
                 category="duplicate_suspect", suggestion="")
    m = break_prf([pred], Truth(pairs=[], breaks=[gold]))
    assert m["f1"] == 0.0
