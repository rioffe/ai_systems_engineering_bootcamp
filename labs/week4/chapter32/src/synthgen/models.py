# pyright: reportMissingImports=false
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    category: str
    fields: dict[str, object]
    expected_outcome: str
    seed_offset: int


@dataclass(frozen=True)
class GroundTruth:
    outcome: str
    fields: dict[str, object]
    source: str
    calculator_version: str


@dataclass(frozen=True)
class Realization:
    question: str
    method: Literal["template", "ollama"]
    template_id: str | None
    model: str | None
    raw_response: str | None


@dataclass(frozen=True)
class ExtractionResult:
    valid: bool
    fields: dict[str, object]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    stage: str
    reasons: tuple[str, ...]
    extracted: dict[str, object]


@dataclass(frozen=True)
class DuplicateDecision:
    duplicate: bool
    kind: Literal["none", "exact", "near"]
    normalized_key: str
    prior_record_id: str | None = None


@dataclass(frozen=True)
class GenerationResult:
    records: tuple[dict[str, Any], ...]
    report: dict[str, Any]
    manifest: dict[str, Any]
    failures: tuple[dict[str, Any], ...] = ()


class GroundTruthCalculator(Protocol):
    @property
    def version(self) -> str:
        raise NotImplementedError

    def calculate(self, scenario: Scenario) -> GroundTruth:
        raise NotImplementedError


class CalculatorRegistry(Protocol):
    def get(self, name: str) -> GroundTruthCalculator:
        raise NotImplementedError
