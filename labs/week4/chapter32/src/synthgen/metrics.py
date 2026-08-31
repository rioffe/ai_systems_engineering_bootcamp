# pyright: reportMissingImports=false
from __future__ import annotations

from collections import Counter
from typing import Any


def _rate(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else round(numerator / denominator, 6)


def build_report(dataset: str, requested: int, attempted: int, records: list[dict[str, Any]], failures: list[dict[str, Any]], duplicates: Counter[str], methods: Counter[str], complete: bool, manifest: str, near_enabled: bool = False) -> dict[str, Any]:
    categories = Counter(row["category"] for row in records)
    return {"report_version": "0.1", "dataset": dataset, "requested": requested, "attempted": attempted, "accepted": len(records), "rejected": len(failures), "complete": complete, "category_counts": dict(sorted(categories.items())), "validation": {"valid": len(records), "rejected": len(failures)}, "duplicates": {"exact": duplicates["exact"], "near": duplicates["near"], "near_deduplication": "enabled" if near_enabled else "disabled"}, "realization_methods": dict(sorted(methods.items())), "metrics": {"acceptance_rate": _rate(len(records), attempted), "validation_rejection_rate": _rate(len(failures), attempted)}, "failures": failures, "manifest": manifest}
