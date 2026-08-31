# pyright: reportMissingImports=false
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .errors import ArtifactError


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write_artifacts(records: list[dict[str, Any]], report: dict[str, Any], manifest: dict[str, Any], output: Path, report_path: Path, manifest_path: Path, allow_partial: bool = False) -> None:
    root = output.parent
    root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".synthgen-", dir=root))
    try:
        staged_output, staged_report, staged_manifest = stage / output.name, stage / report_path.name, stage / manifest_path.name
        staged_output.write_text("".join(stable_json(row) + "\n" for row in records), encoding="utf-8")
        staged_report.write_text(stable_json(report) + "\n", encoding="utf-8")
        manifest = dict(manifest)
        manifest["dataset_sha256"] = sha256_file(staged_output)
        staged_manifest.write_text(stable_json(manifest) + "\n", encoding="utf-8")
        if not report.get("complete", True) and not allow_partial:
            raise ArtifactError("partial artifacts require --allow-partial")
        os.replace(staged_output, output)
        os.replace(staged_report, report_path)
        os.replace(staged_manifest, manifest_path)
    except (OSError, ArtifactError) as exc:
        raise ArtifactError(str(exc)) from exc
    finally:
        for child in stage.glob("*"):
            child.unlink(missing_ok=True)
        stage.rmdir()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ArtifactError(f"cannot read artifact {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ArtifactError(f"artifact {path} must be an object")
    return value
