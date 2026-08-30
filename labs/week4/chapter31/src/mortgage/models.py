from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

QuantityName = Literal["principal", "periodic_rate", "payments", "payment"]


@dataclass(frozen=True)
class FieldEvidence:
    field: QuantityName
    source_text: str
    normalized_value: str
    origin: Literal["explicit", "derived"]


@dataclass(frozen=True)
class Interpretation:
    request: "CalculationRequest | None"
    clarification: str | None
    assumptions: tuple[str, ...]
    evidence: tuple[FieldEvidence, ...]


@dataclass(frozen=True)
class CalculationRequest:
    principal: Decimal | None
    periodic_rate: Decimal | None
    payments: int | None
    payment: Decimal | None
    include_schedule: bool = False
    rounding_places: int = 2


@dataclass(frozen=True)
class AmortizationRow:
    period: int
    payment: Decimal
    principal: Decimal
    interest: Decimal
    balance: Decimal
    adjusted_payoff: bool = False


@dataclass(frozen=True)
class CalculationResult:
    principal: Decimal
    periodic_rate: Decimal
    payments: int
    payment: Decimal
    annual_rate: Decimal
    term_years: Decimal
    total_paid: Decimal
    total_interest: Decimal
    missing_quantity: QuantityName
    schedule: tuple[AmortizationRow, ...] | None = None


@dataclass(frozen=True)
class CalculationError:
    code: str
    message: str
    parameter: str | None = None
    details: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PresentationOptions:
    format: Literal["json", "text"] = "text"
    rounding_places: int = 2
    include_schedule: bool = False


@dataclass(frozen=True)
class ResponseMetadata:
    schema_version: str = "0.2"
    adapter: Literal["direct", "mock", "real"] = "direct"
    assumptions: tuple[str, ...] = ()
    calculation_config: dict[str, str] = field(default_factory=dict)
