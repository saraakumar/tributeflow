"""Eval harness for the review agent.

Runs each golden case through agent.review_entries against the real Claude API
and scores the flag decision as binary classification (precision / recall / F1),
overall and per category. Prompt changes to agent.py can be validated against
this before shipping.

Run:  tributeflow-eval                 (needs ANTHROPIC_API_KEY)
      tributeflow-eval --workers 4 --dataset evals/golden.json
"""

from __future__ import annotations

import argparse
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .models import Entry

log = logging.getLogger(__name__)


@dataclass
class EvalCase:
    id: str
    category: str  # "duplicate" | "wall_mismatch" | "clean"
    should_flag: bool
    existing: list[Entry]
    candidate: Entry
    notes: str = ""


@dataclass
class CaseResult:
    case: EvalCase
    flagged: bool
    reasons: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def correct(self) -> bool:
        return not self.error and self.flagged == self.case.should_flag


def _entry(raw: dict) -> Entry:
    return Entry(
        wall=raw["wall"],
        row_number=raw["row"],
        tribute_name=raw["tribute_name"],
        donor_name=raw.get("donor_name", ""),
        tribute_type=raw.get("tribute_type", ""),
        image_url=raw.get("image_url", ""),
    )


def load_dataset(path: str | Path) -> list[EvalCase]:
    raw = json.loads(Path(path).read_text())
    cases = [
        EvalCase(
            id=c["id"],
            category=c["category"],
            should_flag=c["should_flag"],
            existing=[_entry(e) for e in c["existing"]],
            candidate=_entry(c["candidate"]),
            notes=c.get("notes", ""),
        )
        for c in raw["cases"]
    ]
    ids = [c.id for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case ids in dataset")
    return cases


def run_case(client, model: str, case: EvalCase) -> CaseResult:
    from . import agent  # deferred so scoring stays importable without the SDK

    try:
        flags = agent.review_entries(
            client, model, [case.candidate], case.existing + [case.candidate]
        )
        return CaseResult(case=case, flagged=bool(flags), reasons=[f.problem for f in flags])
    except Exception as exc:  # a crashed case scores as wrong, run continues
        log.exception("case %s errored", case.id)
        return CaseResult(case=case, flagged=False, error=str(exc))


def score(results: list[CaseResult]) -> dict:
    """Precision/recall/F1 for the binary 'flag' decision, plus per-category accuracy."""
    tp = sum(1 for r in results if r.case.should_flag and r.flagged and not r.error)
    fp = sum(1 for r in results if not r.case.should_flag and r.flagged and not r.error)
    fn = sum(1 for r in results if r.case.should_flag and (not r.flagged or r.error))
    tn = sum(1 for r in results if not r.case.should_flag and not r.flagged and not r.error)

    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    by_category: dict[str, dict] = {}
    for r in results:
        bucket = by_category.setdefault(r.case.category, {"total": 0, "correct": 0})
        bucket["total"] += 1
        bucket["correct"] += int(r.correct)

    return {
        "total": len(results),
        "correct": tp + tn,
        "errors": sum(1 for r in results if r.error),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "by_category": by_category,
    }


def cli() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the TributeFlow review agent.")
    parser.add_argument("--dataset", default="evals/golden.json")
    parser.add_argument("--model", default="claude-opus-4-8")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output", default="evals/results.json")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    from anthropic import Anthropic

    client = Anthropic()
    cases = load_dataset(args.dataset)
    print(f"Running {len(cases)} cases on {args.model} ({args.workers} workers)...")

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda c: run_case(client, args.model, c), cases))

    summary = score(results)
    for r in results:
        mark = "OK " if r.correct else ("ERR" if r.error else "MISS")
        detail = r.error or "; ".join(r.reasons) or "(no flag)"
        print(f"  [{mark}] {r.case.id:<28} expected={'flag' if r.case.should_flag else 'pass'} "
              f"got={'flag' if r.flagged else 'pass'}  {detail[:90]}")

    print(f"\nPrecision {summary['precision']}  Recall {summary['recall']}  F1 {summary['f1']}"
          f"  ({summary['correct']}/{summary['total']} correct, {summary['errors']} errors)")
    for cat, b in sorted(summary["by_category"].items()):
        print(f"  {cat:<15} {b['correct']}/{b['total']}")

    Path(args.output).write_text(json.dumps(
        {
            "model": args.model,
            "summary": summary,
            "results": [
                {
                    "id": r.case.id,
                    "category": r.case.category,
                    "should_flag": r.case.should_flag,
                    "flagged": r.flagged,
                    "reasons": r.reasons,
                    "error": r.error,
                }
                for r in results
            ],
        },
        indent=2,
    ) + "\n")
    print(f"\nFull results written to {args.output}")


if __name__ == "__main__":
    cli()
