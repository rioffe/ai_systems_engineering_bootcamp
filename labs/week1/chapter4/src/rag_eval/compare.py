"""Direction-aware regression comparison."""
from __future__ import annotations

# pyright: reportMissingImports=false
from typing import Any

from .metrics import METRIC_KEYS

HIGHER_BETTER = {"accuracy", "precision_at_k", "recall_at_k", "mrr_at_k", "map", "ndcg_at_k", "groundedness", "completeness"}
LOWER_BETTER = set(METRIC_KEYS) - HIGHER_BETTER
DIRECTION_MAP = {key: ("higher" if key in HIGHER_BETTER else "lower") for key in METRIC_KEYS}


def compare_artifacts(baseline: dict[str, Any], current: dict[str, Any], force: bool = False, force_rebuild: bool = False) -> dict[str, Any]:
    if baseline.get("dataset_id") != current.get("dataset_id"):
        raise ValueError("dataset_id mismatch")
    if baseline.get("eval_report_version") != current.get("eval_report_version") and not force:
        raise ValueError("eval report version mismatch")
    metrics: dict[str, Any] = {}
    old = baseline.get("aggregate", {})
    new = current.get("aggregate", {})
    for key in METRIC_KEYS:
        before, after = old.get(key), new.get(key)
        if before is None or after is None:
            metrics[key] = {"baseline": "n/m", "current": "n/m", "delta": "n/m"}
        else:
            delta = after - before if key in HIGHER_BETTER else before - after
            metrics[key] = {"baseline": before, "current": after, "delta": round(delta, 4)}
    return {"eval_report_version": "0.1", "dataset_id": baseline.get("dataset_id"), "metrics": metrics, "by_category": _category_compare(baseline, current), "warnings": (["mixed usage_kind"] if baseline.get("usage_kind") != current.get("usage_kind") else [])}


def _category_compare(baseline: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    groups = set(baseline.get("aggregate", {}).get("by_category", {})) | set(current.get("aggregate", {}).get("by_category", {}))
    for group in sorted(groups):
        result[group] = {}
        left = baseline.get("aggregate", {}).get("by_category", {}).get(group, {})
        right = current.get("aggregate", {}).get("by_category", {}).get(group, {})
        for key in METRIC_KEYS:
            result[group][key] = "n/m" if key not in left or key not in right or left[key] is None or right[key] is None else (right[key] - left[key] if key in HIGHER_BETTER else left[key] - right[key])
    return result
