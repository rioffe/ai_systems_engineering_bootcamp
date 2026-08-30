"""Schema-gated artifact loading."""

# pyright: reportMissingModuleSource=false
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"


class SchemaError(ValueError):
    pass


def validate_document(document: Any, name: str) -> dict[str, Any]:
    try:
        schema = json.loads((SCHEMA_DIR / f"{name}.json").read_text())
        errors = sorted(
            Draft202012Validator(schema).iter_errors(document), key=lambda e: list(e.path)
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise SchemaError(f"cannot load {name} schema: {exc}") from exc
    if errors:
        details = "; ".join(
            f"{'.'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors
        )
        raise SchemaError(f"{name} schema violation: {details}")
    return document


def load_json(path: str | Path, name: str) -> dict[str, Any]:
    try:
        document = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SchemaError(f"JSON artifact error: {exc}") from exc
    return validate_document(document, name)


def load_yaml(path: str | Path, name: str) -> dict[str, Any]:
    try:
        document = yaml.safe_load(Path(path).read_text())
    except (OSError, yaml.YAMLError) as exc:
        raise SchemaError(f"YAML artifact error: {exc}") from exc
    return validate_document(document, name)
