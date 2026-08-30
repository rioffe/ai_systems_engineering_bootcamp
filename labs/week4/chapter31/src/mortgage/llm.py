# pyright: reportMissingImports=false

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Protocol

from .models import CalculationRequest, FieldEvidence, Interpretation
from .tool import calculate_mortgage_tool


class LLMAdapter(Protocol):
    def interpret(self, user_text: str) -> Interpretation: ...
    def explain(self, result: dict[str, Any], assumptions: tuple[str, ...]) -> str: ...


@dataclass(frozen=True)
class AdapterResponse:
    ok: bool
    result: dict[str, Any] | None
    error: dict[str, Any] | None
    interpretation: Interpretation
    explanation: str | None = None


_CURRENCY = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)")
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_YEARS = re.compile(r"(\d+(?:\.\d+)?)\s*(?:years?|yr)")


def _decimal(match: re.Match[str]) -> Decimal:
    return Decimal(match.group(1).replace(",", ""))


class MockLLMAdapter:
    def __init__(self) -> None:
        self.tool_calls = 0

    def interpret(self, user_text: str) -> Interpretation:
        text = user_text.lower()
        if any(term in text for term in ("tax", "insurance", "hoa", "adjustable-rate", "lender quote")):
            return Interpretation(None, "This calculator supports principal and interest only.", (), ())

        amounts = [_decimal(match) for match in _CURRENCY.finditer(user_text)]
        rates = [_decimal(match) / Decimal(100) for match in _PERCENT.finditer(user_text)]
        years = [_decimal(match) for match in _YEARS.finditer(user_text)]
        assumptions: list[str] = []
        evidence: list[FieldEvidence] = []

        if not rates or not years:
            missing = []
            if not rates:
                missing.append("interest rate")
            if not years:
                missing.append("mortgage term")
            return Interpretation(None, f"Please provide the {' and '.join(missing)}.", (), ())

        periodic_rate = rates[0] / Decimal(12)
        payments = years[0] * Decimal(12)
        if payments != payments.to_integral_value():
            return Interpretation(None, "The mortgage term must convert to a whole number of monthly payments.", (), ())
        try:
            payments_int = int(payments)
        except (ArithmeticError, TypeError, ValueError) as exc:
            raise ValueError("MODEL_ERROR: term conversion failed") from exc
        evidence.append(FieldEvidence("periodic_rate", str(rates[0]), str(periodic_rate), "explicit"))
        evidence.append(FieldEvidence("payments", str(years[0]), str(payments_int), "explicit"))

        if "borrow" in text or "afford" in text or "can pay" in text:
            if not amounts:
                return Interpretation(None, "Please provide the monthly payment you can afford.", (), ())
            payment = amounts[-1]
            request = CalculationRequest(None, periodic_rate, payments_int, payment)
            evidence.append(FieldEvidence("payment", str(payment), str(payment), "explicit"))
            return Interpretation(request, None, tuple(assumptions), tuple(evidence))

        down_match = re.search(r"(\d+(?:\.\d+)?)\s*%\s*down", text)
        if down_match and amounts:
            price = amounts[0]
            down = Decimal(down_match.group(1)) / Decimal(100)
            principal = price * (Decimal(1) - down)
            assumptions.append(f"Principal is purchase price less {down_match.group(1)}% down payment.")
            evidence.append(FieldEvidence("principal", str(price), str(principal), "derived"))
        elif amounts:
            principal = amounts[0]
            evidence.append(FieldEvidence("principal", str(principal), str(principal), "explicit"))
        else:
            return Interpretation(None, "Please provide the principal or monthly payment.", (), ())

        if "how long" in text or "how many years" in text or "pay off" in text:
            if len(amounts) < 2:
                return Interpretation(None, "Please provide the payment amount.", tuple(assumptions), tuple(evidence))
            payment = amounts[-1]
            evidence.append(FieldEvidence("payment", str(payment), str(payment), "explicit"))
            return Interpretation(CalculationRequest(principal, periodic_rate, None, payment), None, tuple(assumptions), tuple(evidence))
        if "what rate" in text or "effectively" in text:
            if len(amounts) < 2:
                return Interpretation(None, "Please provide the payment amount.", tuple(assumptions), tuple(evidence))
            payment = amounts[-1]
            evidence.append(FieldEvidence("payment", str(payment), str(payment), "explicit"))
            return Interpretation(CalculationRequest(principal, None, payments_int, payment), None, tuple(assumptions), tuple(evidence))
        evidence.append(FieldEvidence("principal", str(principal), str(principal), "explicit" if not down_match else "derived"))
        return Interpretation(CalculationRequest(principal, periodic_rate, payments_int, None), None, tuple(assumptions), tuple(evidence))

    def explain(self, result: dict[str, Any], assumptions: tuple[str, ...]) -> str:
        if not result.get("ok"):
            error = result["error"]
            return f"The calculator could not complete the request: {error['message']}"
        data = result["result"]
        suffix = f" Assumption: {' '.join(assumptions)}" if assumptions else ""
        return f"The principal-and-interest payment is ${Decimal(data['payment']):,.2f} per month.{suffix}"

    def ask(self, user_text: str) -> AdapterResponse:
        interpretation = self.interpret(user_text)
        if interpretation.clarification:
            if any(term in user_text.lower() for term in ("tax", "insurance", "hoa", "adjustable-rate", "lender quote")):
                error = {"code": "UNSUPPORTED_SCOPE", "message": interpretation.clarification}
                return AdapterResponse(False, None, error, interpretation)
            return AdapterResponse(True, None, None, interpretation, interpretation.clarification)
        if interpretation.request is None:
            raise ValueError("MODEL_ERROR: adapter produced neither request nor clarification")
        self.tool_calls += 1
        request = interpretation.request
        payload = {
            "principal": None if request.principal is None else str(request.principal),
            "periodic_rate": None if request.periodic_rate is None else str(request.periodic_rate),
            "payments": request.payments,
            "payment": None if request.payment is None else str(request.payment),
        }
        tool_result = calculate_mortgage_tool(payload)
        ok = bool(tool_result["ok"])
        return AdapterResponse(
            ok,
            tool_result.get("result"),
            tool_result.get("error"),
            interpretation,
            self.explain(tool_result, interpretation.assumptions) if ok else None,
        )


class RealLLMAdapter:
    """Provider seam with one bounded attempt and no arithmetic fallback."""

    def __init__(self, request_fn: Callable[[str], Interpretation]) -> None:
        self._request_fn = request_fn

    def interpret(self, user_text: str) -> Interpretation:
        try:
            return self._request_fn(user_text)
        except Exception as exc:
            raise ValueError(f"MODEL_ERROR: {exc}") from exc

    def explain(self, result: dict[str, Any], assumptions: tuple[str, ...]) -> str:
        raise ValueError("MODEL_ERROR: real explanation provider is not configured")
