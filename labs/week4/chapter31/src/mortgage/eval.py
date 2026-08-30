from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from time import perf_counter
from typing import Any

OUTCOMES = {
    "calculated", "clarification", "unsupported_scope", "payment_too_low",
    "model_error", "invalid_request", "tool_error",
}


def load_cases(path: str | Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"cannot read dataset: {exc}") from exc
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"dataset line {line_number} is not valid JSON: {exc.msg}") from exc
        if not isinstance(case, dict):
            raise ValueError(f"dataset line {line_number} must be an object")
        if not isinstance(case.get("case_id"), str) or not case["case_id"]:
            raise ValueError(f"dataset line {line_number} requires case_id")
        if not isinstance(case.get("question"), str) or not case["question"]:
            raise ValueError(f"dataset line {line_number} requires question")
        expected = case.get("expected")
        if not isinstance(expected, dict):
            raise ValueError(f"dataset line {line_number} requires expected")
        outcome = expected.get("outcome")
        if outcome not in OUTCOMES:
            raise ValueError(f"dataset line {line_number} has invalid expected outcome")
        cases.append(case)
    if not cases:
        raise ValueError("dataset contains no cases")
    return cases


def _decimal_equal(actual: Any, expected: Any, tolerance: Decimal) -> bool:
    try:
        return abs(Decimal(str(actual)) - Decimal(str(expected))) <= tolerance
    except (InvalidOperation, TypeError, ValueError):
        return False


def _actual_outcome(response: Any) -> str:
    if response.error:
        code = response.error.get("code")
        if code == "UNSUPPORTED_SCOPE":
            return "unsupported_scope"
        if code == "PAYMENT_TOO_LOW":
            return "payment_too_low"
        if code == "MODEL_ERROR":
            return "model_error"
        if code == "TOOL_ERROR":
            return "tool_error"
        return "invalid_request"
    if response.result is None:
        return "clarification"
    return "calculated"


def _actual_intent(response: Any) -> str | None:
    if response.result:
        missing = response.result.get("missing_quantity")
    elif response.interpretation.request is not None:
        request = response.interpretation.request
        missing = next(
            name for name, value in (
                ("principal", request.principal),
                ("periodic_rate", request.periodic_rate),
                ("payments", request.payments),
                ("payment", request.payment),
            ) if value is None
        )
    else:
        return None
    return {
        "principal": "principal",
        "periodic_rate": "rate",
        "payments": "term",
        "payment": "payment",
    }.get(missing)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (ArithmeticError, TypeError, ValueError):
        return default


def _failure_stage(response: Any) -> str:
    if response.error:
        code = response.error.get("code")
        if code == "MODEL_ERROR":
            return "model"
        if code in {"TOOL_ERROR", "INVALID_QUANTITY_COUNT", "INVALID_PRINCIPAL", "INVALID_RATE", "INVALID_PAYMENTS", "INVALID_PAYMENT", "PAYMENT_TOO_LOW", "SOLVER_CONVERGENCE"}:
            return "calculator"
        return "adapter"
    if response.result is None:
        return "interpretation"
    return "none"


def _score_case(case: dict[str, Any], response: Any) -> dict[str, Any]:
    expected = case["expected"]
    actual_outcome = _actual_outcome(response)
    actual_intent = _actual_intent(response)
    checks: dict[str, bool] = {"outcome": actual_outcome == expected["outcome"]}

    expected_intent = expected.get("intent")
    if expected_intent is not None:
        checks["intent"] = actual_intent == expected_intent

    actual_result = response.result or {}
    field_checks: dict[str, bool] = {}
    for field, expected_value in (expected.get("fields") or {}).items():
        field_checks[field] = _decimal_equal(actual_result.get(field), expected_value, Decimal("1e-9"))
    if field_checks:
        checks["fields"] = all(field_checks.values())

    result_checks: dict[str, bool] = {}
    tolerance = Decimal(str((expected.get("result") or {}).get("tolerance", "0.01")))
    for field, expected_value in (expected.get("result") or {}).items():
        if field == "tolerance":
            continue
        result_checks[field] = _decimal_equal(actual_result.get(field), expected_value, tolerance)
    if result_checks:
        checks["numeric_result"] = all(result_checks.values())

    passed = all(checks.values())
    failure_reasons = [name for name, check in checks.items() if not check]
    failure_reasons.extend(
        f"field.{field}" for field, check in field_checks.items() if not check
    )
    failure_reasons.extend(
        f"numeric_result.{field}" for field, check in result_checks.items() if not check
    )
    if passed:
        classification = "none"
    elif not checks.get("outcome", True):
        classification = "outcome_mismatch"
    elif not checks.get("intent", True):
        classification = "intent_mismatch"
    elif not checks.get("fields", True):
        classification = "field_mismatch"
    else:
        classification = "numeric_result_mismatch"
    return {
        "case_id": case["case_id"],
        "category": case.get("category", "uncategorized"),
        "status": "PASS" if passed else "FAIL",
        "question": case["question"],
        "expected": expected,
        "actual": {
            "outcome": actual_outcome,
            "intent": actual_intent,
            "result": actual_result or None,
            "error": response.error,
            "clarification": response.interpretation.clarification,
        },
        "checks": checks,
        "field_checks": field_checks,
        "numeric_checks": result_checks,
        "failure_classification": classification,
        "failure_reasons": failure_reasons,
    }


def evaluate_cases(
    cases: list[dict[str, Any]], adapter: Any, *, adapter_name: str, model_name: str | None,
    include_raw: bool = False,
) -> dict[str, Any]:
    rows = []
    for case in cases:
        before_calls = _safe_int(getattr(adapter, "tool_calls", 0))
        started = perf_counter()
        response = adapter.ask(case["question"])
        duration_ms = _safe_int(round((perf_counter() - started) * 1000))
        after_calls = _safe_int(getattr(adapter, "tool_calls", before_calls), before_calls)
        row = _score_case(case, response)
        row["duration_ms"] = duration_ms
        row["tool_calls"] = max(0, after_calls - before_calls)
        row["failure_stage"] = _failure_stage(response)
        if include_raw:
            excerpt = getattr(adapter, "last_response", None)
            if isinstance(excerpt, str):
                row["model_response_excerpt"] = excerpt[:4000]
        rows.append(row)
    total = len(rows)
    passed = sum(row["status"] == "PASS" for row in rows)
    intent_rows = [row for row in rows if "intent" in row["checks"]]
    field_checks = [value for row in rows for value in row["field_checks"].values()]
    numeric_rows = [row for row in rows if row["numeric_checks"]]
    clarification_rows = [row for row in rows if row["expected"].get("outcome") == "clarification"]
    scope_rows = [row for row in rows if row["expected"].get("outcome") == "unsupported_scope"]
    return {
        "eval_version": "0.1",
        "adapter": adapter_name,
        "model": model_name,
        "summary": {"total": total, "passed": passed, "failed": total - passed},
        "metrics": {
            "intent_accuracy": sum(row["checks"]["intent"] for row in intent_rows) / len(intent_rows) if intent_rows else 1.0,
            "field_accuracy": sum(field_checks) / len(field_checks) if field_checks else 1.0,
            "numeric_result_accuracy": sum(row["checks"].get("numeric_result", False) for row in numeric_rows) / len(numeric_rows) if numeric_rows else 1.0,
            "clarification_accuracy": sum(row["status"] == "PASS" for row in clarification_rows) / len(clarification_rows) if clarification_rows else 1.0,
            "scope_accuracy": sum(row["status"] == "PASS" for row in scope_rows) / len(scope_rows) if scope_rows else 1.0,
        },
        "cases": rows,
    }


def write_report(path: str | Path, report: dict[str, Any]) -> None:
    output = dict(report)
    output.setdefault("eval_version", "0.1")
    try:
        Path(path).write_text(json.dumps(output, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot write evaluation report: {exc}") from exc
