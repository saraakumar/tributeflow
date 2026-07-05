"""Offline tests for the eval harness: dataset integrity and scorer math."""

from pathlib import Path

import pytest

from tributeflow.evals import CaseResult, EvalCase, load_dataset, score
from tributeflow.models import Entry

DATASET = Path(__file__).parent.parent / "evals" / "golden.json"


def test_golden_dataset_loads_and_is_consistent():
    cases = load_dataset(DATASET)
    assert len(cases) >= 15
    for case in cases:
        assert case.category in ("duplicate", "wall_mismatch", "clean")
        # clean cases must not expect a flag, non-clean must
        assert case.should_flag == (case.category != "clean")
        assert case.candidate.tribute_name
        # candidate row must not collide with an existing row on the same wall
        existing_keys = {e.key for e in case.existing}
        assert case.candidate.key not in existing_keys


def test_dataset_covers_both_flag_labels():
    cases = load_dataset(DATASET)
    assert any(c.should_flag for c in cases)
    assert any(not c.should_flag for c in cases)


def _case(should_flag: bool, category: str = "duplicate") -> EvalCase:
    return EvalCase(
        id=f"case-{should_flag}-{category}",
        category=category,
        should_flag=should_flag,
        existing=[],
        candidate=Entry("pets", 2, "Bella", "Smith"),
    )


def test_score_perfect_run():
    results = [
        CaseResult(case=_case(True), flagged=True),
        CaseResult(case=_case(False, "clean"), flagged=False),
    ]
    s = score(results)
    assert s["precision"] == 1.0 and s["recall"] == 1.0 and s["f1"] == 1.0
    assert s["correct"] == 2


def test_score_false_positive_hits_precision():
    results = [
        CaseResult(case=_case(True), flagged=True),
        CaseResult(case=_case(False, "clean"), flagged=True),  # over-flagged
    ]
    s = score(results)
    assert s["precision"] == 0.5
    assert s["recall"] == 1.0
    assert s["confusion"]["fp"] == 1


def test_score_missed_duplicate_hits_recall():
    results = [
        CaseResult(case=_case(True), flagged=False),  # missed
        CaseResult(case=_case(False, "clean"), flagged=False),
    ]
    s = score(results)
    assert s["recall"] == 0.0
    assert s["confusion"]["fn"] == 1


def test_errored_case_counts_as_wrong():
    results = [CaseResult(case=_case(True), flagged=False, error="boom")]
    s = score(results)
    assert s["errors"] == 1
    assert s["correct"] == 0
    assert s["confusion"]["fn"] == 1


def test_duplicate_case_ids_rejected(tmp_path):
    dataset = tmp_path / "bad.json"
    entry = {"wall": "pets", "row": 2, "tribute_name": "A", "donor_name": "B"}
    case = {"id": "x", "category": "clean", "should_flag": False,
            "existing": [], "candidate": entry}
    dataset.write_text(__import__("json").dumps({"cases": [case, case]}))
    with pytest.raises(ValueError, match="duplicate case ids"):
        load_dataset(dataset)
