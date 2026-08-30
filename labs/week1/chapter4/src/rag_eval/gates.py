"""Fail-closed directional regression gates."""
from __future__ import annotations

# pyright: reportMissingImports=false
from typing import Any

from .compare import HIGHER_BETTER
from .metrics import METRIC_KEYS


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def validate_config(config: dict[str, Any]) -> None:
    for gate in config.get("gates", []):
        metric = gate.get("metric")
        if metric not in METRIC_KEYS:
            raise ValueError(f"unknown metric: {metric}")
        bounds = [key for key in ("max_pct_points", "max_pct", "min_value", "max_value") if key in gate]
        if len(bounds) != 1:
            raise ValueError("each gate requires exactly one bound")
        if "max_pct" in bounds and metric in HIGHER_BETTER:
            raise ValueError("max_pct is reserved for latency and cost metrics")
        if "max_pct_points" in bounds and metric.startswith("latency_"):
            raise ValueError("latency metrics require max_pct")


def evaluate_gates(compare_report: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    outcomes = []
    for gate in config["gates"]:
        metric = gate["metric"]
        cell = compare_report.get("metrics", {}).get(metric)
        passed = False
        reason = "missing-metric"
        if isinstance(cell, dict) and cell.get("delta") != "n/m":
            delta = _number(cell["delta"])
            bound = gate.get("max_pct_points", gate.get("max_pct"))
            if "min_value" in gate:
                passed = _number(cell["current"]) >= _number(gate["min_value"])
            elif "max_value" in gate:
                passed = _number(cell["current"]) <= _number(gate["max_value"])
            elif gate["constraint"] == "drop":
                passed = delta >= -_number(bound) if "max_pct_points" in gate else delta >= -_number(bound) / 100 * _number(cell["baseline"])
            else:
                passed = delta >= -_number(bound) if "max_pct_points" in gate else delta >= -_number(bound) / 100 * _number(cell["baseline"])
            reason = "passed" if passed else "constraint-failed"
        outcomes.append({"metric": metric, "passed": passed, "reason": reason})
    return {"gates": outcomes, "passed": all(item["passed"] for item in outcomes)}


def gate_exit_code(report: dict[str, Any]) -> int:
    return 0 if report.get("passed") else 1
