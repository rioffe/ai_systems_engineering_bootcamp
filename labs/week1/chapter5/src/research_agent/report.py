"""Schema-gated canonical trace and drill artifact I/O."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schema import load_json, validate_document


def _canon(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, dict):
        return {key: _canon(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_canon(item) for item in value]
    return value


def write_artifact(path: str | Path, artifact: dict[str, Any], schema: str) -> None:
    value = _canon(artifact)
    validate_document(value, schema)
    Path(path).write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def write_trace(path: str | Path, artifact: dict[str, Any]) -> None:
    write_artifact(path, artifact, "trace")


def load_trace(path: str | Path) -> dict[str, Any]:
    return load_json(path, "trace")


def write_drill_report(path: str | Path, artifact: dict[str, Any]) -> None:
    write_artifact(path, artifact, "drill_report")


def load_drill_report(path: str | Path) -> dict[str, Any]:
    return load_json(path, "drill_report")


def render_trace(artifact: dict[str, Any]) -> str:
    lines = [f"run_id: {artifact['run_id']}", f"question: {artifact['question']}"]
    for step in artifact.get("steps", []):
        lines.append(f"step {step['step']}")
        lines.extend(
            f"  {entry.get('kind')}: {entry.get('tool', entry.get('text', ''))}"
            for entry in step.get("entries", [])
        )
    lines.append(f"termination: {artifact.get('termination', {}).get('reason')}")
    return "\n".join(lines)
