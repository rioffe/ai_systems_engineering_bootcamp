from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from .models import CalculationError

if TYPE_CHECKING:
    from .models import CalculationRequest

INTEGER_TOLERANCE = Decimal("1e-9")
MAX_SCHEDULE_PAYMENTS = 1200


def _finite(value: Decimal | int | None) -> bool:
    return value is None or (isinstance(value, Decimal) and value.is_finite()) or isinstance(value, int)


def validate_request(
    request: CalculationRequest,
    *,
    missing: str | None = None,
    integer_candidate: Decimal | None = None,
) -> CalculationError | None:
    values = (request.principal, request.periodic_rate, request.payments, request.payment)
    missing_count = sum(value is None for value in values)
    if missing_count != 1:
        return CalculationError(
            "INVALID_QUANTITY_COUNT",
            "Exactly one primary quantity must be missing.",
        )

    for name, value in zip(("principal", "periodic_rate", "payments", "payment"), values):
        if not _finite(value):
            return CalculationError("INVALID_" + name.upper(), f"{name} must be finite.", name)

    if request.principal is not None and request.principal <= 0:
        return CalculationError("INVALID_PRINCIPAL", "Principal must be positive.", "principal")
    if request.periodic_rate is not None and request.periodic_rate < 0:
        return CalculationError("INVALID_RATE", "Periodic rate must be non-negative.", "periodic_rate")
    if request.payments is not None and (
        request.payments <= 0
        or not isinstance(request.payments, int)
        or isinstance(request.payments, bool)
    ):
        return CalculationError("INVALID_PAYMENTS", "Payments must be a positive integer.", "payments")
    if request.payment is not None and request.payment <= 0:
        return CalculationError("INVALID_PAYMENT", "Payment must be positive.", "payment")

    if integer_candidate is not None:
        nearest = integer_candidate.to_integral_value()
        if abs(integer_candidate - nearest) > INTEGER_TOLERANCE:
            return CalculationError(
                "INVALID_PAYMENTS",
                "The calculated term is not an integer number of payments.",
                "payments",
                {"reason": "NON_INTEGRAL_TERM"},
            )

    if missing == "payments" and integer_candidate is not None:
        candidate = integer_candidate.to_integral_value()
        if candidate > MAX_SCHEDULE_PAYMENTS and request.include_schedule:
            return CalculationError(
                "INVALID_PAYMENTS",
                f"Payment count exceeds the maximum of {MAX_SCHEDULE_PAYMENTS}.",
                "payments",
            )
    return None
