# pyright: reportMissingImports=false
from __future__ import annotations

from decimal import Decimal
from typing import Any

from .errors import CalculatorError, SpecificationError
from .models import GroundTruth, GroundTruthCalculator, Scenario


class CalculatorRegistryImpl:
    def __init__(self, calculators: dict[str, GroundTruthCalculator] | None = None):
        self._calculators = calculators or {}

    def register(self, name: str, calculator: GroundTruthCalculator) -> None:
        self._calculators[name] = calculator

    def get(self, name: str) -> GroundTruthCalculator:
        try:
            return self._calculators[name]
        except KeyError as exc:
            raise SpecificationError(f"unknown domain/calculator: {name}") from exc


class Chapter31MortgageCalculator:
    version = "chapter31"

    def calculate(self, scenario: Scenario) -> GroundTruth:
        from mortgage.calculator import MortgageCalculator
        from mortgage.models import CalculationRequest
        values = scenario.fields
        try:
            principal = Decimal(str(values["principal"])) if values.get("principal") is not None else None
            rate = Decimal(str(values["annual_rate"])) if values.get("annual_rate") is not None else None
            payments = values.get("payments")
            term = values.get("term_years")
            payment = Decimal(str(values["payment"])) if values.get("payment") is not None else None
            if payments is None and term is not None:
                payments = int(Decimal(str(term)) * 12)
            periodic_rate = Decimal(str(rate)) / 1200 if rate is not None else None
            result = MortgageCalculator().calculate(CalculationRequest(principal, periodic_rate, int(payments) if payments is not None else None, payment, False, 2))
            fields: dict[str, object] = {"payments": result.payments, "payment": result.payment, "annual_rate": result.annual_rate, "principal": result.principal, "term_years": result.term_years}
            return GroundTruth("calculated", fields, "mortgage", self.version)
        except Exception as exc:
            message = str(exc)
            if "PAYMENT_TOO_LOW" in message:
                return GroundTruth("payment_too_low", {}, "mortgage", self.version)
            raise CalculatorError(message, details={"scenario_id": scenario.scenario_id}) from exc


def calculate_truth(scenario: Scenario, registry: CalculatorRegistryImpl, domain: str) -> GroundTruth:
    return registry.get(domain).calculate(scenario)


def default_registry() -> CalculatorRegistryImpl:
    registry = CalculatorRegistryImpl()
    registry.register("mortgage", Chapter31MortgageCalculator())
    return registry
