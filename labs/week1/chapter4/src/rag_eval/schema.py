"""Schema-gated JSON and YAML artifact loading."""
# pyright: reportMissingModuleSource=false

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"


class SchemaError(ValueError):
    """Raised when an artifact cannot be parsed or fails its schema."""


def _schema_path(name: str) -> Path:
    path = SCHEMA_DIR / f"{name}.json"
    if not path.is_file():
        raise SchemaError(f"unknown schema: {name}")
    return path


def validate_document(document: Any, schema_name: str) -> Any:
    try:
        schema = json.loads(_schema_path(schema_name).read_text())
        errors = sorted(
            Draft202012Validator(schema).iter_errors(document), key=lambda error: list(error.path)
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise SchemaError(f"cannot load schema {schema_name}: {exc}") from exc
    if errors:
        details = "; ".join(
            f"{'.'.join(map(str, error.path)) or '<root>'}: {error.message}" for error in errors
        )
        raise SchemaError(f"{schema_name} schema violation: {details}")
    return document


def load_json(path: str | Path, schema_name: str) -> dict[str, Any]:
    try:
        document = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SchemaError(f"JSON artifact error: {exc}") from exc
    return validate_document(document, schema_name)


def load_yaml(path: str | Path, schema_name: str) -> dict[str, Any]:
    try:
        document = yaml.safe_load(Path(path).read_text())
    except (OSError, yaml.YAMLError) as exc:
        raise SchemaError(f"YAML artifact error: {exc}") from exc
    return validate_document(document, schema_name)
