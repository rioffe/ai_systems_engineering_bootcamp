# pyright: reportMissingImports=false

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from .calculator import (
    SOLVER_MAX_ITERATIONS,
    SOLVER_TOLERANCE,
    MortgageCalculator,
)
from .models import CalculationError, CalculationRequest, ResponseMetadata


def _error_from_exception(exc: ValueError) -> CalculationError:
    code, _, detail = str(exc).partition(":")
    return CalculationError(code or "TOOL_ERROR", detail.strip() or str(exc))


def calculate(
    request: CalculationRequest,
    *,
    adapter: str = "direct",
    assumptions: tuple[str, ...] = (),
) -> dict:
    metadata = ResponseMetadata(
        adapter=adapter,  # type: ignore[arg-type]
        assumptions=assumptions,
        calculation_config={
            "solver_tolerance": str(SOLVER_TOLERANCE),
            "solver_max_iterations": str(SOLVER_MAX_ITERATIONS),
        },
    )
    try:
        result = MortgageCalculator().calculate(request)
    except ValueError as exc:
        error = _error_from_exception(exc)
        return {"ok": False, "result": None, "error": error, "metadata": metadata}
    return {"ok": True, "result": result, "error": None, "metadata": metadata}


def parse_decimal(value: object, field: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field} must be finite")
    return parsed
