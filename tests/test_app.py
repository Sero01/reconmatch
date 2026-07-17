from app import run_reconcile, show_sample


def test_sample_returns_non_empty_tables():
    matches, breaks, summary = show_sample()
    assert matches and breaks
    assert "auto-matched" in summary


def test_run_reconcile_on_sample_csvs():
    matches, breaks, summary = run_reconcile(
        "samples/ledger.csv", "samples/statement.csv")
    assert matches
    assert "auto-matched" in summary


def test_malformed_csv_returns_message_not_exception(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("not,a,ledger\n1,2,3\n")
    matches, breaks, summary = run_reconcile(str(bad), "samples/statement.csv")
    assert matches == [] and breaks == []
    assert summary.startswith("❌")


def test_missing_inputs_prompts_upload():
    matches, breaks, summary = run_reconcile(None, None)
    assert matches == [] and "Upload" in summary
