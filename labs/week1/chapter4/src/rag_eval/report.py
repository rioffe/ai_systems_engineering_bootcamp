"""Canonical artifact serialization and human renderers."""
# pyright: reportMissingImports=false

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schema import load_json, validate_document


def _canonical(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, dict):
        return {key: _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    return value


def write_json_artifact(path: str | Path, artifact: dict[str, Any], schema_name: str) -> None:
    normalized = _canonical(artifact)
    validate_document(normalized, schema_name)
    Path(path).write_text(json.dumps(normalized, sort_keys=True, separators=(",", ":")) + "\n")


def load_artifact(path: str | Path, schema_name: str, force: bool = False) -> dict[str, Any]:
    artifact = load_json(path, schema_name)
    if schema_name in {"eval", "compare"} and artifact.get("eval_report_version") != "0.1" and not force:
        raise ValueError("eval report version mismatch")
    return artifact


def write_dataset_report(path: str | Path, report: dict[str, Any]) -> None:
    write_json_artifact(path, report, "dataset")


def write_eval_artifact(path: str | Path, artifact: dict[str, Any]) -> None:
    write_json_artifact(path, artifact, "eval")


def write_compare_report(path: str | Path, report: dict[str, Any]) -> None:
    write_json_artifact(path, report, "compare")


def write_gate_report(path: str | Path, report: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(_canonical(report), sort_keys=True, separators=(",", ":")) + "\n")


def write_judge_check_report(path: str | Path, report: dict[str, Any]) -> None:
    write_gate_report(path, report)


def write_pair_report(path: str | Path, report: dict[str, Any]) -> None:
    write_gate_report(path, report)


def render_compare_table(report: dict[str, Any]) -> str:
    lines = ["metric | baseline | current | delta", "--- | ---: | ---: | ---:"]
    for metric, values in report.get("metrics", {}).items():
        lines.append(f"{metric} | {values.get('baseline', 'n/m')} | {values.get('current', 'n/m')} | {values.get('delta', 'n/m')}")
    return "\n".join(lines)


def render_summary(artifact: dict[str, Any]) -> str:
    aggregate = artifact.get("aggregate", {})
    return f"dataset={artifact.get('dataset_id')} usage={artifact.get('usage_kind')} accuracy={aggregate.get('accuracy', 'n/m')}"
