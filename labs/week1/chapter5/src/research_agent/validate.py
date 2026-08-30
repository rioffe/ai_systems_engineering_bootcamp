"""Decision and final-report validation gates."""

# pyright: reportMissingImports=false
from __future__ import annotations

from typing import Any

from .schema import validate_document


def validate_decision(decision: Any, registry: Any) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    try:
        validate_document(decision, "decision")
    except ValueError as exc:
        errors.append({"error": "invalid_arguments", "field": "decision", "message": str(exc)})
        return errors
    if decision["type"] == "tool_call":
        tool = decision["tool"]
        if tool not in registry.specs:
            errors.append(
                {"error": "invalid_arguments", "field": "tool", "message": f"unknown tool: {tool}"}
            )
        for field in (
            registry.specs.get(tool, {}).input_schema.get("required", [])
            if hasattr(registry.specs.get(tool), "input_schema")
            else []
        ):
            if field not in decision["arguments"]:
                errors.append(
                    {"error": "invalid_arguments", "field": field, "message": "field is required"}
                )
    return errors


def validate_final_report(
    report: Any, retrieved_ids: set[str], conflict_markers: list[dict[str, Any]] | None = None
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    try:
        validate_document(report, "report")
    except ValueError as exc:
        errors.append({"error": "invalid_report", "field": "report", "message": str(exc)})
        return errors
    for citation in report["citations"]:
        if citation not in retrieved_ids:
            errors.append(
                {
                    "error": "invalid_report",
                    "field": "citations",
                    "message": f"not retrieved: {citation}",
                }
            )
    required = {
        str(marker.get("quantity"))
        for marker in conflict_markers or []
        if marker.get("quantity") is not None
    }
    covered = {
        str(conflict.get("quantity"))
        for conflict in report["conflicts"]
        if conflict.get("quantity") is not None
    }
    for quantity in sorted(required - covered):
        errors.append(
            {
                "error": "invalid_report",
                "field": "conflicts",
                "message": f"missing conflict: {quantity}",
            }
        )
    return errors
