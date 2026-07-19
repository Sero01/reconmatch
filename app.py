"""Gradio demo: bundled sample pair (free) + upload two CSVs to reconcile."""
from __future__ import annotations

import csv
from pathlib import Path

import gradio as gr

from reconmatch.breaks import reconcile
from reconmatch.schema import (ReconReport, RowError, load_ledger_csv,
                               load_statement_csv)

MAX_BYTES = 1024 * 1024  # 1 MB per CSV
SAMPLE_DIR = Path("samples")

MATCH_HEADERS = ["Ledger entries", "Statement line(s)", "Tier", "Confidence"]
BREAK_HEADERS = ["Side", "Record", "Category", "Related", "Suggestion"]


class InputError(Exception):
    """A rejected upload; message is safe to show the user."""


def _checked_load(path: Path, loader, kind: str):
    if path.stat().st_size > MAX_BYTES:
        raise InputError(f"{kind} file too large (max 1 MB).")
    try:
        return loader(path)
    except RowError as e:
        raise InputError(f"{kind} CSV problem — {e}") from e
    except (UnicodeDecodeError, csv.Error) as e:
        raise InputError(f"{kind} file is not valid CSV.") from e


def _render(report: ReconReport):
    matches = [[", ".join(m.entry_ids), ", ".join(m.line_ids), m.tier,
                round(m.confidence, 3)]
               for m in report.matches]
    breaks = [[b.side, b.record_id, b.category, b.related_id or "", b.suggestion]
              for b in report.breaks]
    s = report.summary
    summary = (f"**{s['n_matched_entries']}/{s['n_entries']}** ledger entries "
               f"auto-matched (**{s['match_rate']:.0%}**) · **{s['n_breaks']}** "
               f"breaks flagged · {s['n_lines']} statement lines")
    return matches, breaks, summary


def run_reconcile(ledger_file, statement_file):
    if not ledger_file or not statement_file:
        return [], [], "Upload both a ledger CSV and a statement CSV."
    try:
        ledger = _checked_load(Path(ledger_file), load_ledger_csv, "Ledger")
        lines = _checked_load(Path(statement_file), load_statement_csv, "Statement")
    except InputError as e:
        return [], [], f"❌ {e}"
    return _render(reconcile(ledger, lines))


def show_sample():
    report = ReconReport.model_validate_json((SAMPLE_DIR / "report.json").read_text())
    return _render(report)


with gr.Blocks(title="ReconMatch — reconciliation matching") as demo:
    gr.Markdown("# ReconMatch\nMatches bank-statement lines to internal ledger "
                "entries — exact, date-windowed, and split payments — then "
                "classifies every unmatched item as a break with a resolution "
                "hint. Deterministic: same inputs, same output, zero inference "
                "cost.")
    with gr.Tab("Sample (precomputed)"):
        gr.Markdown("A synthetic 40-entry ledger against its bank statement "
                    "(date lags, split payments, bank fees, a keying error, a "
                    "duplicate).")
        btn_s = gr.Button("Load sample reconciliation")
        summary_s = gr.Markdown()
        gr.Markdown("### Matches")
        matches_s = gr.Dataframe(headers=MATCH_HEADERS)
        gr.Markdown("### Breaks")
        breaks_s = gr.Dataframe(headers=BREAK_HEADERS)
        btn_s.click(show_sample, None, [matches_s, breaks_s, summary_s])
    with gr.Tab("Reconcile your own"):
        gr.Markdown("Two CSVs, each `id,date,description,amount[,reference]`. "
                    "Amounts signed: negative = money out. Max 1 MB each.")
        ledger_up = gr.File(file_types=[".csv"], label="Ledger CSV")
        statement_up = gr.File(file_types=[".csv"], label="Statement CSV")
        btn_u = gr.Button("Reconcile")
        summary_u = gr.Markdown()
        gr.Markdown("### Matches")
        matches_u = gr.Dataframe(headers=MATCH_HEADERS)
        gr.Markdown("### Breaks")
        breaks_u = gr.Dataframe(headers=BREAK_HEADERS)
        btn_u.click(run_reconcile, [ledger_up, statement_up],
                    [matches_u, breaks_u, summary_u], concurrency_limit=2)

demo.queue(max_size=10)
if __name__ == "__main__":
    demo.launch()
