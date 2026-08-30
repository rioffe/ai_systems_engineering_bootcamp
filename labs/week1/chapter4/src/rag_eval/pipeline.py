"""End-to-end evaluation orchestration."""
# pyright: reportMissingImports=false

from __future__ import annotations

from dataclasses import is_dataclass
from typing import Any

from .aoe import build_index, run_case
from .evaluator import evaluate_case
from .metrics import aggregate_metrics


def run_dataset(dataset: Any, corpus_dir: str, index_flags: dict[str, Any] | None = None, query_flags: dict[str, Any] | None = None, labels: dict[str, Any] | None = None) -> dict[str, Any]:
    index = build_index(corpus_dir, index_flags or {})
    rows = []
    for case in dataset.cases:
        try:
            result = run_case(case, index, query_flags or {})
            row = evaluate_case(case, result, labels)
        except Exception as exc:  # noqa: BLE001
            row = {"case_id": case.case_id, "category": case.category, "verdict": {"status": "FAIL"}, "metrics": {}, "failure_classification": "GENERATION_FAILURE", "trace": {"error": str(exc)}}
        if is_dataclass(row):
            row = dict(row.__dict__)
        row["category"] = case.category
        row["difficulty"] = case.difficulty
        rows.append(row)
    metric_rows = [{**row.get("metrics", {}), "category": row["category"], "difficulty": row.get("difficulty")} for row in rows]
    aggregate = aggregate_metrics(metric_rows, [case.category for case in dataset.cases], [case.difficulty for case in dataset.cases] if any(case.difficulty for case in dataset.cases) else None)
    return {"eval_report_version": "0.1", "dataset_id": dataset.dataset_id, "usage_kind": "synthetic", "judge_role": "mock", "capabilities": query_flags or {}, "cases": rows, "aggregate": aggregate}
