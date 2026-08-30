"""Deterministic checks layered over the authoritative AoE verdict."""
# pyright: reportMissingImports=false

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .failure import classify_failure
from .metrics import case_metrics


def _value(obj: Any, key: str, default: Any = None) -> Any:
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


class DeterministicChecks:
    def check(self, aoe_result: Any) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = []
        parsed = _value(aoe_result, "parsed_answer")
        valid = isinstance(parsed, dict) and parsed is not None
        checks.append({"name": "answer_schema", "passed": valid})
        retrieved = set(_value(aoe_result, "retrieved_chunks", []) or [])
        citations = _value(parsed, "citations", []) if valid else []
        cited_ids = [(_value(citation, "chunk_id") or "") for citation in citations]
        membership = all(chunk_id in retrieved for chunk_id in cited_ids)
        checks.append({"name": "citation_membership", "passed": membership})
        return checks


def map_verdict(verdict: Any, *, parse_blocked: bool = False) -> dict[str, Any]:
    source = dict(verdict) if isinstance(verdict, dict) else vars(verdict)
    if parse_blocked:
        return {**source, "status": "PARSE_BLOCKED", "ch3_status": source.get("status")}
    original = source.get("status", "ERROR")
    mapped = {"SCORED": "PASS", "ERROR": "FAIL", "PARTIAL": "FAIL"}.get(original, "FAIL")
    return {**source, "status": mapped, "ch3_status": original}


@dataclass
class EvaluationRow:
    case_id: str
    category: str
    verdict: dict[str, Any]
    checks: list[dict[str, Any]]
    failure_classification: str | None
    metrics: dict[str, Any]
    trace: dict[str, Any] = field(default_factory=dict)


def evaluate_case(case: Any, aoe_result: Any, labels: dict[str, Any] | None = None) -> EvaluationRow:
    checks = DeterministicChecks().check(aoe_result)
    parsed = _value(aoe_result, "parsed_answer")
    blocked = not all(check["passed"] for check in checks[:1])
    verdict = map_verdict(_value(aoe_result, "verdict", {}), parse_blocked=blocked)
    case_id = _value(case, "case_id", "")
    disagreements: set[str] = set()
    if labels and case_id in labels:
        label = labels[case_id]
        if any(label.get(key) != verdict.get(key) for key in ("correct", "supported", "complete") if key in label):
            disagreements.add(case_id)
    classification = classify_failure(verdict["status"], _value(aoe_result, "failure_stage"), case_id, disagreements)
    metrics = case_metrics(case, {"verdict": verdict, "parsed_answer": parsed, **(vars(aoe_result) if hasattr(aoe_result, "__dict__") else aoe_result)})
    trace = {key: _value(aoe_result, key) for key in ("retrieved_chunks", "scores", "raw_output", "parsed_answer", "failure_stage", "usage_tokens", "latency_ms", "cost_usd")}
    return EvaluationRow(case_id, _value(case, "category", ""), verdict, checks, classification, metrics, trace)
