"""E4 - N:M recovery by amount-cell components. REVIEW-GRADE, never auto.

Supersedes the earlier "documented ceiling / negative result" version of this
module, which claimed N:M was unrecoverable on BenchRec. That claim was WRONG
and is retracted: it generalized from two hand-sampled non-conserving groups and
from the SOTA reference's 0% on multi-A. The population does conserve (~91%),
and a large share of N:M IS recoverable - but only a specific share, which this
module measures honestly instead of rounding up to "N:M works".

GROUND TRUTH (verified, not assumed)
  A B record's ``targetAllocation`` is the SET of A_allocation strings of every A
  record in its match group - a bracketed comma-list when the group has >1 A,
  a plain string when it has exactly 1, blank when the B is truly unmatched.
  Verified on all 68,975 train B's: parsed target == group's A-allocation set for
  100%. Allocation strings contain no comma and no bracket, so the list parse is
  unambiguous. 2,787 groups repeat an allocation string, so the target is a SET
  (duplicates collapse) - scoring therefore compares sets of strings.

METHOD
  Partition all records into cells keyed by ``(currency, account, value_date,
  amount)``; a cell with at least one A and one B of opposite direction emits a
  prediction, and every B in that cell predicts the SET of A allocations in the
  same cell.

  This is the "connected components over equality edges" method stated in the
  plan, and it is written as a plain cell partition because the two are provably
  identical here: a record has exactly one amount and one date, so it lies in
  exactly ONE cell, and no edge can ever leave it. That identity is the whole
  limitation - see gate 2 below - so the code shows it rather than burying it in
  a union-find that could never union anything across amounts.

  (Signs: A carries CR=+/DR=-, B carries DR=+/CR=-, so true partners share a
  SIGNED amount and hold opposite direction letters. The direction filter is
  consequently a no-op on BenchRec, but it is applied explicitly because it is a
  real relational constraint on data where sign conventions differ.)

WHAT THIS MODULE DOES *NOT* DO (deliberate scope, per review 2026-07-21)
  * It does NOT claim a cross-amount joining rule. Equality-only edges cannot
    join records of different amounts, so a true group spanning >1 amount is
    NECESSARILY fragmented into >=2 components, each predicting a strict subset.
    Multi-amount N:M is an OPEN GAP; no rule is proposed or validated here.
  * It does NOT emit an auto-match. Every prediction is dispositioned
    SUGGESTED_FOR_REVIEW. The observable ambiguity/abstention predicate and the
    ablation to an auto-grade (>=99.8% Wilson LB) subset are a SEPARATE later
    step; the precision reported here is review-grade evidence, nothing more.
  * It does NOT compare against the MatcherByChatGPT reference. Those figures are
    from `eval`; these are group-safe train dev/val, and train/eval multi-A
    prevalence differs sharply (27% vs 5.6%). A comparison needs one frozen
    same-split eval run under this same exact-set scoring.

SCORING (gate 1): strict exact-set. A B record is CORRECT iff its COMPLETE
predicted allocation set equals its target set. Subsets score as failures and are
reported separately, because a strict subset is exactly the fragmentation
signature that a headline recall number would otherwise hide.

Rigor matches the rest of the ladder: group-safe 70/30 dev/val split by matchId,
cardinality stratification, single-/multi-amount decomposition, Wilson 95% lower
bound on precision, provenance header.

Run:    uv run python experiments/benchrec/groups.py
Emits:  data/benchrec/artifacts/e4_groups.md
        data/benchrec/artifacts/e4_components.csv   (per-component evidence)
"""
from __future__ import annotations

import csv
import os
from collections import Counter, defaultdict

from bench_io import load_train, provenance_lines
from bench_stats import Z_95, assign_split, cardinality_class, wilson_lower_bound

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "..", "data", "benchrec")
TRAIN = os.path.join(DATA, "BenchRec_cash_v1.0_train.csv")
ART = os.path.join(DATA, "artifacts")

SPLITS = ("dev", "val")
STRATA = ("1:1", "1:N", "N:1", "N:M", "unmatched")

# Every prediction this module emits carries this disposition. There is no auto
# path here by construction (see module docstring).
DISPOSITION = "SUGGESTED_FOR_REVIEW"

# Per-B outcome taxonomy under strict exact-set scoring.
EXACT = "EXACT"
STRICT_SUBSET = "STRICT_SUBSET"      # fragmentation: predicted ⊂ target
STRICT_SUPERSET = "STRICT_SUPERSET"  # cell merged foreign A's: predicted ⊃ target
OVERLAP = "OVERLAP"                  # intersecting, neither contains the other
DISJOINT = "DISJOINT"                # predicted something, shares nothing
NO_PREDICTION = "NO_PREDICTION"      # cell had no eligible A
OUTCOMES = (EXACT, STRICT_SUBSET, STRICT_SUPERSET, OVERLAP, DISJOINT, NO_PREDICTION)


def parse_target(raw: str) -> frozenset[str]:
    """Parse ``targetAllocation`` into a set of A_allocation strings.

    Bracketed comma-list when the group holds >1 A, plain string for exactly 1,
    blank for a truly-unmatched B. Safe because allocations contain no comma or
    bracket (verified over the full train split).
    """
    t = raw.strip()
    if not t:
        return frozenset()
    if t.startswith("[") and t.endswith("]"):
        t = t[1:-1]
    return frozenset(part for part in t.split(",") if part)


def cell_key(rec) -> tuple:
    """The equality cell a record belongs to. Each record lies in exactly one."""
    return (rec.currency, rec.account, rec.value_date, rec.minor)


def build_components(pop) -> dict[tuple, dict[str, list]]:
    """Partition a population into ``(currency, account, value_date, amount)`` cells.

    Returns cell_key -> {"A": [...], "B": [...]}. Equivalent to connected
    components over equality edges (see module docstring): no component can span
    two amounts, so components and cells coincide.
    """
    cells: dict[tuple, dict[str, list]] = defaultdict(lambda: {"A": [], "B": []})
    for rec in pop["A"]:
        cells[cell_key(rec)]["A"].append(rec)
    for rec in pop["B"]:
        cells[cell_key(rec)]["B"].append(rec)
    return cells


def predict(cell) -> frozenset[str]:
    """Predicted allocation set for every B in a cell.

    The A side of the cell, restricted to A's whose direction opposes the B side
    (a real match is opposite DR/CR). Empty set == no prediction.
    """
    b_dirs = {b.direction for b in cell["B"]}
    return frozenset(a.allocation for a in cell["A"] if a.direction not in b_dirs)


def classify(predicted: frozenset[str], target: frozenset[str]) -> str:
    """Strict exact-set outcome for one B record."""
    if not predicted:
        return NO_PREDICTION
    if predicted == target:
        return EXACT
    if predicted < target:
        return STRICT_SUBSET
    if predicted > target:
        return STRICT_SUPERSET
    return OVERLAP if predicted & target else DISJOINT


# --- Truth-side bookkeeping ------------------------------------------------------

def truth_maps(groups) -> tuple[dict, dict, dict]:
    """Return (b_target, b_card, b_amountclass) keyed by B rec_id.

    ``amount_class`` is a property of the TRUE group: 'single-amount' when every
    record in the group carries one and the same signed amount, else
    'multi-amount'. This is the decomposition gate 2 requires - the method can
    only ever recover the single-amount kind.
    """
    b_target: dict[str, frozenset[str]] = {}
    b_card: dict[str, str] = {}
    b_amount: dict[str, str] = {}
    for g in groups.values():
        card = cardinality_class(len(g["A"]), len(g["B"]))
        amounts = {r.minor for r in g["A"] + g["B"]}
        amount_class = "single-amount" if len(amounts) == 1 else "multi-amount"
        for b in g["B"]:
            b_target[b.rec_id] = parse_target(b.target)
            b_card[b.rec_id] = card
            b_amount[b.rec_id] = amount_class
    return b_target, b_card, b_amount


def split_groups(groups) -> dict[str, dict]:
    out: dict[str, dict] = {s: {} for s in SPLITS}
    for match_id, g in groups.items():
        out[assign_split(match_id)][match_id] = g
    return out


def population(split_truth) -> dict[str, list]:
    pop: dict[str, list] = {"A": [], "B": []}
    for g in split_truth.values():
        pop["A"].extend(g["A"])
        pop["B"].extend(g["B"])
    return pop


# --- Scoring ---------------------------------------------------------------------

def score(cells, b_target, b_card, b_amount) -> tuple[dict, list[dict]]:
    """Strict exact-set scoring, stratified, plus the per-component evidence rows.

    Returns (stats, evidence). ``stats`` maps a stratum label to a Counter of
    outcomes; strata are the cardinality classes plus, for multi-A groups, the
    single-/multi-amount decomposition.
    """
    stats: dict[str, Counter] = defaultdict(Counter)
    evidence: list[dict] = []

    for key, cell in sorted(cells.items(), key=lambda kv: (kv[0][2], kv[0][3])):
        if not cell["B"]:
            continue
        predicted = predict(cell)
        outcomes = Counter()
        for b in cell["B"]:
            target = b_target[b.rec_id]
            outcome = classify(predicted, target)
            outcomes[outcome] += 1
            for stratum in (b_card[b.rec_id], f"{b_card[b.rec_id]} / {b_amount[b.rec_id]}"):
                stats[stratum][outcome] += 1
            stats["ALL"][outcome] += 1
        if predicted:
            evidence.append(_evidence_row(key, cell, predicted, outcomes, b_card, b_amount))
    return stats, evidence


def _evidence_row(key, cell, predicted, outcomes, b_card, b_amount) -> dict:
    """One component's evidence (gate 4).

    Observable columns describe the component as the method sees it. The
    ``true_*``/``outcome_*`` columns are ORACLE-derived and exist for analysis
    only - nothing in the method may branch on them.
    """
    currency, account, value_date, minor = key
    b_ids = [b.rec_id for b in cell["B"]]
    a_ids = [a.rec_id for a in cell["A"]]
    true_groups = {b_card[b] for b in b_ids}
    return {
        # --- observable ---
        "component_id": f"{currency}|{account}|{value_date}|{minor}",
        "currency": currency,
        "account": account,
        "value_date": value_date,
        "amount_minor": minor,
        "n_a": len(a_ids),
        "n_b": len(b_ids),
        "shape": f"{len(a_ids)}:{len(b_ids)}",
        "amount_multiset": f"{{{minor}}}x{len(a_ids) + len(b_ids)}",
        "distinct_amounts": 1,
        "n_predicted_allocations": len(predicted),
        "a_ids": " ".join(sorted(a_ids)),
        "b_ids": " ".join(sorted(b_ids)),
        "disposition": DISPOSITION,
        # --- oracle, analysis only ---
        "true_cardinalities": " ".join(sorted(true_groups)),
        "true_amount_classes": " ".join(sorted({b_amount[b] for b in b_ids})),
        "collision_reason": _collision_reason(outcomes),
        "n_b_exact": outcomes[EXACT],
        "n_b_total": sum(outcomes.values()),
        **{f"outcome_{o.lower()}": outcomes[o] for o in OUTCOMES},
    }


def _collision_reason(outcomes: Counter) -> str:
    """Why a component's B's did not all land EXACT (oracle diagnosis)."""
    if outcomes[EXACT] == sum(outcomes.values()):
        return "NONE_ALL_EXACT"
    reasons = []
    if outcomes[STRICT_SUBSET]:
        reasons.append("FRAGMENTED_MULTI_AMOUNT_GROUP")
    if outcomes[STRICT_SUPERSET]:
        reasons.append("MERGED_FOREIGN_RECORDS")
    if outcomes[OVERLAP]:
        reasons.append("PARTIAL_CELL_COLLISION")
    if outcomes[DISJOINT]:
        reasons.append("WRONG_CELL")
    return "+".join(reasons) if reasons else "MIXED"


def rates(counter: Counter) -> tuple[int, int, int, float, float, float]:
    """(total, predicted, exact, recall, precision, wilson_lb) for one stratum."""
    total = sum(counter.values())
    predicted = total - counter[NO_PREDICTION]
    exact = counter[EXACT]
    recall = exact / total if total else 0.0
    precision = exact / predicted if predicted else 0.0
    lb = wilson_lower_bound(exact, predicted, Z_95) if predicted else 0.0
    return total, predicted, exact, recall, precision, lb


# --- Reporting -------------------------------------------------------------------

def _stratum_table(stats, order) -> list[str]:
    lines = [
        "| stratum | B records | predicted | exact | recall | precision | Wilson 95% LB |",
        "|---|---|---|---|---|---|---|",
    ]
    for label in order:
        if label not in stats:
            continue
        total, predicted, exact, recall, precision, lb = rates(stats[label])
        lines.append(
            f"| {label} | {total:,} | {predicted:,} | {exact:,} | "
            f"{recall:.2%} | {precision:.2%} | {lb:.2%} |")
    return lines


def _failure_table(stats, order) -> list[str]:
    lines = [
        "| stratum | EXACT | STRICT_SUBSET | STRICT_SUPERSET | OVERLAP | DISJOINT | NO_PREDICTION |",
        "|---|---|---|---|---|---|---|",
    ]
    for label in order:
        if label not in stats:
            continue
        c = stats[label]
        lines.append(f"| {label} | " + " | ".join(f"{c[o]:,}" for o in OUTCOMES) + " |")
    return lines


def write_evidence(evidence, path) -> None:
    if not evidence:
        return
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(evidence[0].keys()))
        writer.writeheader()
        writer.writerows(evidence)


def main() -> None:
    _a, _b, groups = load_train(TRAIN)
    b_target, b_card, b_amount = truth_maps(groups)
    per_split = split_groups(groups)

    stats: dict[str, dict] = {}
    evidence: dict[str, list] = {}
    for split in SPLITS:
        cells = build_components(population(per_split[split]))
        stats[split], evidence[split] = score(cells, b_target, b_card, b_amount)

    order = ["ALL"]
    for card in STRATA:
        order.append(card)
        for amount_class in ("single-amount", "multi-amount"):
            order.append(f"{card} / {amount_class}")

    lines = [
        "# E4 - N:M recovery by amount-cell components (REVIEW-GRADE)",
        "",
        "> Generated by `experiments/benchrec/groups.py`.",
        "> **Supersedes the earlier 'documented ceiling' artifact, whose conclusion that N:M is",
        "> unrecoverable was WRONG and is retracted.** N:M is partly recoverable - but only the",
        "> single-amount kind, which this artifact separates out rather than averaging over.",
        "",
        "**Scoring (gate 1): strict exact-set.** A B record counts as correct iff its COMPLETE",
        "predicted allocation set equals its `targetAllocation` set. A strict subset is a FAILURE",
        "and is reported as its own column, because subsets are the fragmentation signature that a",
        "single headline recall number would otherwise conceal.",
        "",
        "**Disposition: every prediction below is `SUGGESTED_FOR_REVIEW`.** No auto-match is",
        "claimed or emitted. These precisions are review-grade evidence. The observable",
        "ambiguity/abstention predicate, and the ablation to an auto-grade (>=99.8% Wilson LB)",
        "subset, are a separate later step and are NOT attempted here.",
        "",
        "**No comparison to the MatcherByChatGPT reference is made.** Those figures are from",
        "`eval`; these are group-safe `train` dev/val, and multi-A prevalence differs sharply",
        "between them. That comparison requires one frozen same-split eval run under this scoring.",
        "",
        *provenance_lines({"train": TRAIN}, {
            "split": "matchId 70/30 (group-safe)",
            "dev_frac": 0.7,
            "component": "(currency, account, value_date, amount) + opposite DR/CR",
            "scoring": "strict exact-set (complete predicted set == target set)",
            "disposition": DISPOSITION,
        }),
        "",
        "## Method",
        "",
        "Partition every record into a cell keyed by `(currency, account, value_date, amount)`; a",
        "cell holding at least one A and one B of opposite direction emits a prediction, and each B",
        "in the cell predicts the SET of A allocations in that same cell.",
        "",
        "This is the plan's 'connected components over equality edges' method. It is implemented as",
        "a plain cell partition because the two are **provably identical**: a record carries exactly",
        "one amount and one date, so it belongs to exactly one cell, and no equality edge can leave",
        "that cell.",
        "",
        "### Gate 2 - how do different amount cells join into one N:M candidate?",
        "",
        "**They do not. No cross-amount joining rule is implemented or claimed.**",
        "",
        "This is structural, not an oversight: equality-only edges cannot link records of different",
        "amounts, so a true group spanning more than one amount is NECESSARILY split across >=2",
        "components, each of which can only ever predict a strict subset of that group's target set.",
        "Every such B is scored a failure below (`STRICT_SUBSET`). A cross-amount rule - e.g.",
        "clustering the A side by a shared reference token, then linking A-cluster to B-cluster by",
        "equal amount-multiset - is **UNSPECIFIED and UNVALIDATED**. Multi-amount N:M is an OPEN GAP.",
        "",
        "The decomposition tables below therefore carry the real result; the aggregate row does not.",
        "",
    ]

    for split in SPLITS:
        lines += [
            f"## Results - {split}",
            "",
            *_stratum_table(stats[split], order),
            "",
            f"### Failure decomposition - {split}",
            "",
            *_failure_table(stats[split], order),
            "",
        ]

    lines += [
        "## Reading the result",
        "",
        "- **Single-amount groups are what this method recovers.** There the component coincides",
        "  with the true group, so the complete target set is reproduced.",
        "- **Multi-amount groups fragment.** The `STRICT_SUBSET` column is exactly that failure: the",
        "  component predicts the A's sharing its own amount, while the target is the whole group.",
        "- **The aggregate `ALL` row is not the headline.** It mixes a solved stratum with an open",
        "  one, and its value moves with cardinality prevalence rather than with method quality.",
        "- **Precision here is review-grade.** It is well short of the 99.8% Wilson-LB auto bar, and",
        "  nothing in this module abstains; separating an auto-grade subset is the next step.",
        "",
        "## Evidence (gate 4)",
        "",
        "`e4_components.csv` carries one row per emitted component: component id, cell coordinates,",
        "amount multiset, shape, A/B record ids, predicted-set size, and disposition (all observable",
        "to the method), plus oracle-derived analysis columns - true cardinalities, true amount",
        "classes, collision reason, and the per-outcome B counts including whether the target set was",
        "reproduced exactly. The oracle columns are for analysis only; the method branches on none",
        "of them.",
        "",
        "## Status",
        "",
        "- Single-amount N:M: recoverable by amount-cell components, at review-grade precision.",
        "- Multi-amount N:M: **open**. No rule proposed, none validated.",
        "- Auto-grade policy: **not attempted here** (separate step).",
        "- Reference comparison: **not made here** (needs a frozen same-split eval run).",
    ]

    os.makedirs(ART, exist_ok=True)
    out_md = os.path.join(ART, "e4_groups.md")
    with open(out_md, "w") as f:
        f.write("\n".join(lines) + "\n")
    out_csv = os.path.join(ART, "e4_components.csv")
    write_evidence(evidence["dev"] + evidence["val"], out_csv)

    print(f"wrote {out_md}")
    print(f"wrote {out_csv}")
    for split in SPLITS:
        for label in ("ALL", "1:1", "N:M", "N:M / single-amount", "N:M / multi-amount"):
            if label not in stats[split]:
                continue
            total, predicted, exact, recall, precision, lb = rates(stats[split][label])
            print(f"{split:>3} | {label:<22} n={total:>6,} recall={recall:>7.2%} "
                  f"prec={precision:>7.2%} LB={lb:>7.2%}")


if __name__ == "__main__":
    main()
