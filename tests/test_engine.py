import random
from datetime import date
from decimal import Decimal

from reconmatch.datagen import generate_pair
from reconmatch.engine import MatchConfig, desc_sim, match
from reconmatch.schema import LedgerEntry, StatementLine


def d(day: int) -> date:
    return date(2026, 3, day)


def entry(eid="E1", day=5, desc="Acme Ltd invoice 44",
          amount="-1250.50", ref=None) -> LedgerEntry:
    return LedgerEntry(entry_id=eid, date=d(day), description=desc,
                       amount=Decimal(amount), reference=ref)


def line(lid="S1", day=5, desc="POS ACME LTD",
         amount="-1250.50", ref=None) -> StatementLine:
    return StatementLine(line_id=lid, date=d(day), description=desc,
                         amount=Decimal(amount), reference=ref)


# --- tier 1 ---

def test_exact_match_high_confidence():
    [m] = match([entry()], [line()])
    assert m.line_ids == ["S1"] and m.tier == 1 and m.confidence >= 0.95


def test_reference_match_beats_description():
    [m] = match([entry(ref="INV-44")], [line(desc="XYZ", ref="INV-44")])
    assert m.tier == 1 and m.confidence == 1.0


def test_different_amount_never_tier1():
    assert match([entry()], [line(amount="-1250.51")]) == []


def test_sign_matters():
    assert match([entry(amount="100.00")], [line(amount="-100.00")]) == []


# --- greedy assignment / determinism ---

def test_no_line_reused():
    e1, e2 = entry("E1"), entry("E2")
    only = line("S1")
    ms = match([e1, e2], [only])
    assert len(ms) == 1


def test_shuffle_invariance():
    ledger, lines, _ = generate_pair(random.Random(11))
    base = match(ledger, lines)
    rng = random.Random(0)
    shuffled_l, shuffled_s = ledger[:], lines[:]
    rng.shuffle(shuffled_l)
    rng.shuffle(shuffled_s)
    assert match(shuffled_l, shuffled_s) == base


# --- tier 2 ---

def test_lagged_settlement_matches_tier2():
    [m] = match([entry()], [line(day=7)])
    assert m.tier == 2 and 0.6 <= m.confidence < 0.95


def test_beyond_window_no_match():
    assert match([entry()], [line(day=9)]) == []


def test_dissimilar_description_no_tier2():
    assert match([entry()], [line(day=6, desc="UNRELATED PAYEE")]) == []


def test_tier1_preferred_over_tier2():
    same_day = line("S1", day=5)
    lagged = line("S2", day=6)
    [m] = match([entry()], [same_day, lagged])
    assert m.line_ids == ["S1"] and m.tier == 1


# --- tier 3 ---

def test_three_way_split_matches():
    parts = [line("S1", amount="-500.00"), line("S2", amount="-400.50"),
             line("S3", amount="-350.00")]
    [m] = match([entry()], parts)
    assert m.tier == 3
    assert m.line_ids == ["S1", "S2", "S3"]  # sorted
    assert m.confidence < 0.95


def test_split_beyond_max_k_no_match():
    parts = [line(f"S{i}", amount="-312.625") for i in range(1, 5)]
    assert match([entry()], parts, MatchConfig(max_split=3)) == []


def test_tier1_wins_lines_from_split_candidates():
    exact = line("S0")
    parts = [line("S1", amount="-1000.00"), line("S2", amount="-250.50")]
    ms = match([entry()], [exact, *parts])
    assert [m for m in ms if m.tier == 1]


# --- end to end on generated data ---

def test_engine_precision_floor_on_generated_data():
    ledger, lines, truth = generate_pair(random.Random(42), n_entries=60)
    pred = {(tuple(sorted(m.entry_ids)), tuple(sorted(m.line_ids)))
            for m in match(ledger, lines)}
    gold = {(tuple(sorted(p.entry_ids)), tuple(sorted(p.line_ids)))
            for p in truth.pairs}
    assert pred, "engine matched nothing"
    precision = len(pred & gold) / len(pred)
    assert precision >= 0.95, precision


def test_desc_sim_casefolds():
    assert desc_sim("Acme Ltd", "ACME LTD") == 1.0
