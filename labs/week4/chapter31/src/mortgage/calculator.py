# pyright: reportMissingImports=false

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, localcontext
from typing import cast

from .models import CalculationRequest, CalculationResult, QuantityName
from .validation import INTEGER_TOLERANCE, validate_request

SOLVER_LOWER_BOUND = Decimal("0")
SOLVER_UPPER_BOUND = Decimal("1")
SOLVER_TOLERANCE = Decimal("1e-12")
SOLVER_MAX_ITERATIONS = 100


def _error(code: str, detail: str = "") -> ValueError:
    return ValueError(f"{code}: {detail}".rstrip())


def calculate_payment(principal: Decimal, periodic_rate: Decimal, payments: int) -> Decimal:
    if periodic_rate == 0:
        return principal / Decimal(payments)
    with localcontext() as context:
        context.prec = 50
        growth = (Decimal(1) + periodic_rate) ** payments
        return principal * periodic_rate * growth / (growth - Decimal(1))


def calculate_principal(payment: Decimal, periodic_rate: Decimal, payments: int) -> Decimal:
    if periodic_rate == 0:
        return payment * Decimal(payments)
    with localcontext() as context:
        context.prec = 50
        growth = (Decimal(1) + periodic_rate) ** payments
        return payment * (growth - Decimal(1)) / (periodic_rate * growth)


def calculate_exact_payments(principal: Decimal, periodic_rate: Decimal, payment: Decimal) -> Decimal:
    if periodic_rate == 0:
        return principal / payment
    if payment <= principal * periodic_rate:
        raise _error("PAYMENT_TOO_LOW", "payment must exceed first-period interest")
    with localcontext() as context:
        context.prec = 50
        return ((payment / (payment - principal * periodic_rate)).ln() /
                (Decimal(1) + periodic_rate).ln())


def calculate_payments(principal: Decimal, periodic_rate: Decimal, payment: Decimal) -> int:
    candidate = calculate_exact_payments(principal, periodic_rate, payment)
    try:
        return int(candidate.to_integral_value(rounding=ROUND_CEILING))
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise _error("INVALID_PAYMENTS", "term is not representable as an integer") from exc


def calculate_rate(
    principal: Decimal,
    payment: Decimal,
    payments: int,
    *,
    tolerance: Decimal = SOLVER_TOLERANCE,
    max_iterations: int = SOLVER_MAX_ITERATIONS,
) -> Decimal:
    def residual(rate: Decimal) -> Decimal:
        return calculate_payment(principal, rate, payments) - payment

    lower = SOLVER_LOWER_BOUND
    upper = SOLVER_UPPER_BOUND
    lower_value = residual(lower)
    upper_value = residual(upper)
    if abs(lower_value) <= tolerance:
        return lower
    if abs(upper_value) <= tolerance:
        return upper
    if lower_value * upper_value > 0:
        raise _error("SOLVER_CONVERGENCE", "rate bounds do not bracket a root")

    for _ in range(max_iterations):
        midpoint = (lower + upper) / Decimal(2)
        midpoint_value = residual(midpoint)
        if abs(midpoint_value) <= tolerance or upper - lower <= tolerance:
            return midpoint
        if lower_value * midpoint_value <= 0:
            upper, upper_value = midpoint, midpoint_value
        else:
            lower, lower_value = midpoint, midpoint_value
    raise _error("SOLVER_CONVERGENCE", "maximum iterations exceeded")


class MortgageCalculator:
    def calculate(self, request: CalculationRequest) -> CalculationResult:
        error = validate_request(request)
        if error is not None:
            raise _error(error.code, error.message)

        missing = next(
            name for name, value in (
                ("principal", request.principal),
                ("periodic_rate", request.periodic_rate),
                ("payments", request.payments),
                ("payment", request.payment),
            ) if value is None
        )
        principal = request.principal
        periodic_rate = request.periodic_rate
        payments = request.payments
        payment = request.payment
        exact_payments: Decimal | None = None

        if missing == "payment":
            if principal is None or periodic_rate is None or payments is None:
                raise _error("INVALID_QUANTITY_COUNT")
            payment = calculate_payment(principal, periodic_rate, payments)
        elif missing == "principal":
            if payment is None or periodic_rate is None or payments is None:
                raise _error("INVALID_QUANTITY_COUNT")
            principal = calculate_principal(payment, periodic_rate, payments)
        elif missing == "payments":
            if principal is None or periodic_rate is None or payment is None:
                raise _error("INVALID_QUANTITY_COUNT")
            exact_payments = calculate_exact_payments(principal, periodic_rate, payment)
            payments = calculate_payments(principal, periodic_rate, payment)
        else:
            if principal is None or payment is None or payments is None:
                raise _error("INVALID_QUANTITY_COUNT")
            periodic_rate = calculate_rate(principal, payment, payments)

        if principal is None or periodic_rate is None or payments is None or payment is None:
            raise _error("INVALID_QUANTITY_COUNT")
        if exact_payments is None:
            exact_payments = Decimal(payments)
        with localcontext() as context:
            context.prec = 50
            exact_term_years = exact_payments / Decimal(12)
        schedule = None
        if request.include_schedule:
            from .amortization import amortize
            schedule = amortize(principal, periodic_rate, payments, payment)
        total_paid = payment * Decimal(payments)
        return CalculationResult(
            principal=principal,
            periodic_rate=periodic_rate,
            payments=payments,
            payment=payment,
            annual_rate=periodic_rate * Decimal(12),
            term_years=exact_term_years,
            total_paid=total_paid,
            total_interest=total_paid - principal,
            missing_quantity=cast("QuantityName", missing),
            schedule=schedule,
            exact_payments=exact_payments,
            exact_term_years=exact_term_years,
        )
