# pyright: reportMissingImports=false
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from .errors import SpecificationError


@dataclass(frozen=True)
class FieldDescriptor:
    name: str
    type: str
    required: bool = True
    nullable: bool = False
    values: tuple[Any, ...] = ()
    minimum: Decimal | None = None
    maximum: Decimal | None = None
    distribution: dict[str, Any] | None = None


@dataclass(frozen=True)
class Category:
    name: str
    weight: float
    fields: dict[str, Any]


@dataclass(frozen=True)
class DatasetConfig:
    name: str
    domain: str
    size: int = 1000
    seed: int | None = None
    max_attempts: int | None = None
    output: str = "generated.jsonl"
    report: str = "generated.report.json"
    manifest: str = "generated.manifest.json"


@dataclass(frozen=True)
class DatasetSpecification:
    dataset: DatasetConfig
    fields: tuple[FieldDescriptor, ...]
    categories: tuple[Category, ...]
    constraints: tuple[str, ...]
    realization: dict[str, Any]
    raw: dict[str, Any]
    spec_hash: str

    @property
    def field_map(self) -> dict[str, FieldDescriptor]:
        return {f.name: f for f in self.fields}


def _decimal(value: Any, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise SpecificationError(f"{label} must be numeric") from exc
    if not result.is_finite():
        raise SpecificationError(f"{label} must be finite")
    return result


def _integer(value: Any, label: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise SpecificationError(f"{label} must be an integer") from exc
    if str(value) not in {str(result), f"{result}.0"}:
        raise SpecificationError(f"{label} must be an integer")
    return result


def _normalized_json(value: Any) -> dict[str, Any]:
    try:
        result = json.loads(json.dumps(value, sort_keys=True, default=str))
    except (TypeError, ValueError) as exc:
        raise SpecificationError(f"cannot normalize specification: {exc}") from exc
    if not isinstance(result, dict):
        raise SpecificationError("normalized specification must be a mapping")
    return result


def load_spec(path: Path) -> DatasetSpecification:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SpecificationError(f"cannot read specification {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise SpecificationError("specification must be a mapping")
    missing = [key for key in ("dataset", "schema", "categories") if key not in raw]
    if missing:
        raise SpecificationError(f"missing required sections: {', '.join(missing)}")
    dataset_raw = raw["dataset"]
    if not isinstance(dataset_raw, dict) or not dataset_raw.get("name") or not dataset_raw.get("domain"):
        raise SpecificationError("dataset.name and dataset.domain are required")
    size = _integer(dataset_raw.get("size", 1000), "dataset.size")
    if size < 1:
        raise SpecificationError("dataset.size must be positive")
    seed = dataset_raw.get("seed")
    if seed is not None:
        seed = _integer(seed, "dataset.seed")
    max_attempts = dataset_raw.get("max_attempts")
    if max_attempts is not None and _integer(max_attempts, "max_attempts") < 1:
        raise SpecificationError("max_attempts must be finite and positive")
    dataset = DatasetConfig(str(dataset_raw["name"]), str(dataset_raw["domain"]), size, seed, _integer(max_attempts, "max_attempts") if max_attempts is not None else None, str(dataset_raw.get("output", "generated.jsonl")), str(dataset_raw.get("report", "generated.report.json")), str(dataset_raw.get("manifest", "generated.manifest.json")))
    field_raw = raw["schema"].get("fields") if isinstance(raw["schema"], dict) else None
    if not isinstance(field_raw, list) or not field_raw:
        raise SpecificationError("schema.fields must be a non-empty list")
    fields = []
    for item in field_raw:
        if not isinstance(item, dict) or not all(k in item for k in ("name", "type", "required", "nullable")):
            raise SpecificationError("each field descriptor requires name, type, required, and nullable")
        kind = str(item["type"])
        if kind not in {"string", "decimal", "integer", "enum"}:
            raise SpecificationError(f"unknown field type: {kind}")
        values = tuple(item.get("values", ()))
        if kind == "enum" and not values:
            raise SpecificationError(f"enum field {item['name']} requires values")
        fields.append(FieldDescriptor(str(item["name"]), kind, bool(item["required"]), bool(item["nullable"]), values, _decimal(item["minimum"], f"{item['name']}.minimum") if "minimum" in item else None, _decimal(item["maximum"], f"{item['name']}.maximum") if "maximum" in item else None, item.get("distribution")))
    categories_raw = raw["categories"]
    if not isinstance(categories_raw, dict) or not categories_raw:
        raise SpecificationError("categories must contain at least one category")
    try:
        categories = tuple(Category(str(name), float(value.get("weight", 0)), dict(value)) for name, value in categories_raw.items() if isinstance(value, dict))
    except (TypeError, ValueError, OverflowError) as exc:
        raise SpecificationError("category weights must be numeric") from exc
    if len(categories) != len(categories_raw) or any(c.weight <= 0 for c in categories) or abs(sum(c.weight for c in categories) - 1.0) > 1e-9:
        raise SpecificationError("category weights must be positive and sum to 1.0")
    realization = raw.get("realization", {"method": "template", "max_regenerations": 3})
    if realization.get("method", "template") not in {"template", "ollama"}:
        raise SpecificationError("unknown realization method")
    normalized = _normalized_json(raw)
    spec_hash = "sha256:" + hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return DatasetSpecification(dataset, tuple(fields), categories, tuple(raw.get("constraints", ())), realization, raw, spec_hash)


def normalize_spec(spec: DatasetSpecification) -> dict[str, Any]:
    return _normalized_json(spec.raw)


def validate_spec(spec: DatasetSpecification, registry: Any) -> None:
    registry.get(spec.dataset.domain)
    for field in spec.fields:
        if field.distribution:
            method = field.distribution.get("distribution")
            if method not in {"uniform", "lognormal", "choice", "values"}:
                raise SpecificationError(f"unknown distribution: {method}")
            if method in {"uniform", "lognormal"} and not all(k in field.distribution for k in (("min", "max") if method == "uniform" else ("mu", "sigma"))):
                raise SpecificationError(f"incomplete {method} distribution for {field.name}")
