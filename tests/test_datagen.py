import random

from reconmatch.datagen import generate_pair, write_dataset
from reconmatch.schema import load_ledger_csv, load_statement_csv


def test_truth_accounts_for_every_ledger_entry():
    ledger, lines, truth = generate_pair(random.Random(7))
    matched = {i for p in truth.pairs for i in p.entry_ids}
    broken = {b.record_id for b in truth.breaks if b.side == "ledger"}
    assert matched | broken == {e.entry_id for e in ledger}
    assert matched.isdisjoint(broken)


def test_truth_accounts_for_every_statement_line():
    ledger, lines, truth = generate_pair(random.Random(7))
    in_pairs = {i for p in truth.pairs for i in p.line_ids}
    broken = {b.record_id for b in truth.breaks if b.side == "statement"}
    assert in_pairs | broken == {line.line_id for line in lines}


def test_pair_amounts_balance_exactly():
    ledger, lines, truth = generate_pair(random.Random(7))
    by_id = {line.line_id: line for line in lines}
    entries = {e.entry_id: e for e in ledger}
    for p in truth.pairs:
        total_lines = sum(by_id[i].amount for i in p.line_ids)
        total_entries = sum(entries[i].amount for i in p.entry_ids)
        assert total_lines == total_entries, p


def test_perturbations_all_present_at_scale():
    _, _, truth = generate_pair(random.Random(5), n_entries=200)
    cats = {b.category for b in truth.breaks}
    assert {"missing_in_ledger", "missing_in_statement",
            "amount_mismatch_suspect", "duplicate_suspect"} <= cats
    assert any(len(p.line_ids) > 1 for p in truth.pairs)  # splits exist


def test_deterministic_for_seed():
    assert generate_pair(random.Random(3)) == generate_pair(random.Random(3))


def test_write_dataset_round_trips(tmp_path):
    write_dataset(tmp_path, seed=11)
    ledger = load_ledger_csv(tmp_path / "ledger.csv")
    lines = load_statement_csv(tmp_path / "statement.csv")
    assert ledger and lines
    assert (tmp_path / "truth.json").exists()
