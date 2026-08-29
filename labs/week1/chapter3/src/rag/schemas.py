"""JSON-Schema gate for emitted result artifacts (R-09 / R-10 / I-010).

The pipeline's Answer (R-09) and the Judge's Verdict (R-10) are structured
output, so they carry fixed JSON-Schema contracts in schemas/ (the ch1/ch2
C-05/C-09 analog). Per I-010 / T-08 a case reaches COMPLETED / JUDGED only
through a schema-valid object: out-of-range confidence or a missing required
field is rejected and retried, then ERROR -- never COMPLETED.

The jsonschema library (a declared project dep) drives the gate when importable;
otherwise the lab degrades to a dependency-free structural validator over the
SAME draft-2020-12 schemas so it runs offline. using_jsonschema() reports which
path is live and is surfaced as the report's schema_validation field.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, is_dataclass
from typing import Any

_SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "schemas")

try:
    from jsonschema import Draft202012Validator

    HAVE_JSONSCHEMA: bool = True
except ImportError:
    Draft202012Validator = None  # type: ignore[assignment]
    HAVE_JSONSCHEMA: bool = False


class SchemaError(ValueError):
    pass


def _load(name: str) -> dict:
    path = os.path.join(_SCHEMA_DIR, name)
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise SchemaError(f"cannot load schema {name!r} from {path!r}: {exc}") from exc


def answer_schema() -> dict:
    return _load("answer.json")


def verdict_schema() -> dict:
    return _load("verdict.json")


def using_jsonschema() -> bool:
    return HAVE_JSONSCHEMA


def _type_ok(value: Any, ty: str) -> bool:
    if ty == "object":
        return isinstance(value, dict)
    if ty == "array":
        return isinstance(value, list)
    if ty == "string":
        return isinstance(value, str)
    if ty == "boolean":
        return isinstance(value, bool)
    if ty == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if ty == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if ty == "null":
        return value is None
    return False


def _structural(value: Any, schema: dict, path: str, errors: list[str]) -> None:
    t = schema.get("type")
    types = t if isinstance(t, (list, tuple)) else [t] if t else []
    if types:
        ok = any(_type_ok(value, ty) for ty in types)
        if not ok:
            errors.append(f"{path}: expected type {types}, got {type(value).__name__}")
            return
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} not in enum {list(schema['enum'])}")
    if isinstance(value, dict):
        for req in schema.get("required", []):
            if req not in value:
                errors.append(f"{path}: missing required property {req!r}")
        subs = schema.get("properties", {})
        for key, sub in subs.items():
            if key in value:
                _structural(value[key], sub, f"{path}.{key}", errors)
        if not schema.get("additionalProperties", True):
            for key in value:
                if key not in subs:
                    errors.append(f"{path}: additional property {key!r} not allowed")
        mp = schema.get("minProperties")
        if mp is not None and len(value) < mp:
            errors.append(f"{path}: fewer than {mp} properties")
    if isinstance(value, list):
        items = schema.get("items")
        if items is not None:
            for i, el in enumerate(value):
                _structural(el, items, f"{path}[{i}]", errors)
        mi = schema.get("minItems")
        if mi is not None and len(value) < mi:
            errors.append(f"{path}: fewer than {mi} items")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        lo = schema.get("minimum")
        hi = schema.get("maximum")
        if lo is not None and value < lo:
            errors.append(f"{path}: {value} < minimum {lo}")
        if hi is not None and value > hi:
            errors.append(f"{path}: {value} > maximum {hi}")


def _validate_against(obj: Any, schema: dict, source: str) -> None:
    if HAVE_JSONSCHEMA and Draft202012Validator is not None:
        try:
            Draft202012Validator(schema).validate(obj)
        except Exception as exc:
            raise SchemaError(f"{source} failed jsonschema: {exc}") from exc
        return
    errors: list[str] = []
    _structural(obj, schema, "<root>", errors)
    if errors:
        raise SchemaError(f"{source} failed schema validation: " + "; ".join(errors))


def _jsonable(obj: Any) -> Any:
    result = asdict(obj) if is_dataclass(obj) else obj  # type: ignore[call-overload]
    return result


def validate_answer(obj: Any) -> None:
    _validate_against(_jsonable(obj), answer_schema(), "answer")


def validate_verdict(obj: Any) -> None:
    _validate_against(_jsonable(obj), verdict_schema(), "verdict")


def emit(out_dir: str, kind: str, obj: Any) -> str:
    if kind == "answer":
        validate_answer(obj)
    elif kind == "verdict":
        validate_verdict(obj)
    else:
        raise SchemaError(f"unknown artifact kind {kind!r} (expected answer|verdict)")
    dst = os.path.join(out_dir, f"{kind}.json")
    try:
        with open(dst, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(_jsonable(obj), indent=2))
    except OSError as exc:
        raise SchemaError(f"cannot write {dst!r}: {exc}") from exc
    return dst
