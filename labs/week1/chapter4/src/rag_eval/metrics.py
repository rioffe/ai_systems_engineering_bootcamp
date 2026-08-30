"""Pure evaluation-vector metric calculations."""
from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

METRIC_KEYS = [
    "accuracy", "precision_at_k", "recall_at_k", "mrr_at_k", "map", "ndcg_at_k",
    "groundedness", "completeness", "hallucination_rate", "latency_p50", "latency_p90",
    "latency_p95", "latency_p99", "cost_per_success",
]


def _top(items: Sequence[str], k: int) -> list[str]:
    return list(items[: max(0, k)])


def precision_at_k(relevant: Iterable[str], retrieved: Sequence[str], k: int) -> float:
    top = _top(retrieved, k)
    return len(set(top) & set(relevant)) / k if k > 0 else 0.0


def recall_at_k(relevant: Iterable[str], retrieved: Sequence[str], k: int) -> float:
    gold = set(relevant)
    return len(gold & set(_top(retrieved, k))) / len(gold) if gold else 0.0


def mrr_at_k(relevant: Iterable[str], retrieved: Sequence[str], k: int) -> float:
    gold = set(relevant)
    for rank, item in enumerate(_top(retrieved, k), 1):
        if item in gold:
            return 1.0 / rank
    return 0.0


def average_precision(relevant: Iterable[str], retrieved: Sequence[str], k: int) -> float:
    gold = set(relevant)
    if not gold:
        return 0.0
    hits = 0
    total = 0.0
    for rank, item in enumerate(_top(retrieved, k), 1):
        if item in gold:
            hits += 1
            total += hits / rank
    return total / len(gold)


def ndcg_at_k(relevant: Iterable[str], retrieved: Sequence[str], k: int) -> float:
    gold = set(relevant)
    top = _top(retrieved, k)
    if not gold or not top:
        return 0.0
    dcg = sum(1 / math.log2(rank + 1) for rank, item in enumerate(top, 1) if item in gold)
    ideal = min(len(gold), len(top))
    idcg = sum(1 / math.log2(rank + 1) for rank in range(1, ideal + 1))
    return dcg / idcg if idcg else 0.0


def near_rank_percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile / 100 * len(ordered)))
    return _as_float(ordered[min(rank, len(ordered)) - 1])


def _get(value: Any, key: str, default: Any = None) -> Any:
    return value.get(key, default) if isinstance(value, Mapping) else getattr(value, key, default)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def case_metrics(case: Any, result: Any, k: int = 5) -> dict[str, float | None]:
    verdict = _get(result, "verdict", {}) or {}
    parsed = _get(result, "parsed_answer")
    blocked = _get(result, "status") == "PARSE_BLOCKED" or parsed is None
    correct = False if blocked else bool(_get(verdict, "correct", _get(result, "correct", False)))
    supported = False if blocked else bool(_get(verdict, "supported", _get(result, "supported", False)))
    complete = False if blocked else bool(_get(verdict, "complete", _get(result, "complete", False)))
    claims = 0 if blocked else _as_int(_get(verdict, "total_factual_claims", _get(result, "total_factual_claims", 0)) or 0)
    unsupported = 0 if blocked else len(_get(verdict, "unsupported_claims", _get(result, "unsupported_claims", [])) or [])
    gold_facts = list(_get(case, "gold_facts", []) or [])
    reflected = _get(result, "reflected_gold_facts", []) or []
    retrieved = _get(result, "retrieved_chunks", []) or []
    relevant = _get(case, "relevant_chunks", []) or []
    latency = _as_float(_get(result, "latency_ms", 0.0) or 0.0)
    cost = _get(result, "cost_usd")
    return {
        "accuracy": _as_float(correct),
        "precision_at_k": precision_at_k(relevant, retrieved, k),
        "recall_at_k": recall_at_k(relevant, retrieved, k),
        "mrr_at_k": mrr_at_k(relevant, retrieved, k),
        "map": average_precision(relevant, retrieved, k),
        "ndcg_at_k": ndcg_at_k(relevant, retrieved, k),
        "groundedness": 1.0 if claims == 0 else _as_float(supported) if claims == 1 else (claims - unsupported) / claims,
        "completeness": 1.0 if not gold_facts else (len(set(reflected) & set(gold_facts)) / len(gold_facts) if reflected else _as_float(complete)),
        "hallucination_rate": 0.0 if claims == 0 else unsupported / claims,
        "latency_ms": latency,
        "cost_usd": None if cost is None else _as_float(cost),
    }


def aggregate_metrics(rows: Sequence[Mapping[str, Any]], categories: Sequence[str] | None = None, difficulties: Sequence[str] | None = None) -> dict[str, Any]:
    def mean(key: str, values: Sequence[Mapping[str, Any]]) -> float | None:
        nums = [_as_float(row[key]) for row in values if row.get(key) is not None]
        return sum(nums) / len(nums) if nums else (None if key == "cost_per_success" else 0.0)

    output: dict[str, Any] = {}
    for key in METRIC_KEYS:
        if key.startswith("latency_"):
            pct = _as_int(key.rsplit("_", 1)[1][1:])
            output[key] = near_rank_percentile([_as_float(row.get("latency_ms", 0)) for row in rows], pct)
        elif key == "cost_per_success":
            costs = [_as_float(row["cost_usd"]) for row in rows if row.get("cost_usd") is not None and row.get("accuracy")]
            output[key] = sum(costs) / len(costs) if costs else None
        else:
            output[key] = mean(key, rows)
    by_category: dict[str, Any] = {}
    for category in sorted(set(categories or [str(row.get("category", "")) for row in rows])):
        subset = [row for row in rows if row.get("category") == category]
        by_category[category] = {key: mean(key, subset) for key in METRIC_KEYS if not key.startswith("latency_")}
    output["by_category"] = by_category
    if difficulties is not None:
        output["by_difficulty"] = {
            difficulty: {key: mean(key, [row for row in rows if row.get("difficulty") == difficulty]) for key in METRIC_KEYS if not key.startswith("latency_")}
            for difficulty in sorted(set(difficulties))
        }
    return output
