# pyright: reportMissingImports=false

from __future__ import annotations

from decimal import Decimal, localcontext

from .models import AmortizationRow
from .validation import MAX_SCHEDULE_PAYMENTS


def amortize(
    principal: Decimal,
    periodic_rate: Decimal,
    payments: int,
    payment: Decimal,
) -> tuple[AmortizationRow, ...]:
    if payments <= 0 or payments > MAX_SCHEDULE_PAYMENTS:
        raise ValueError(f"INVALID_PAYMENTS: must be between 1 and {MAX_SCHEDULE_PAYMENTS}")
    if principal <= 0:
        raise ValueError("INVALID_PRINCIPAL: principal must be positive")
    if periodic_rate < 0:
        raise ValueError("INVALID_RATE: periodic rate must be non-negative")
    if payment <= 0:
        raise ValueError("INVALID_PAYMENT: payment must be positive")

    rows: list[AmortizationRow] = []
    with localcontext() as context:
        context.prec = 50
        balance = principal
        for period in range(1, payments + 1):
            interest = balance * periodic_rate
            if payment <= interest and period < payments:
                raise ValueError("PAYMENT_TOO_LOW: payment does not cover interest")
            regular_principal = payment - interest
            adjusted = period == payments or regular_principal >= balance
            if adjusted:
                principal_component = balance
                row_payment = principal_component + interest
                balance = Decimal("0")
            else:
                principal_component = regular_principal
                row_payment = payment
                balance -= principal_component
            rows.append(
                AmortizationRow(
                    period=period,
                    payment=row_payment,
                    principal=principal_component,
                    interest=interest,
                    balance=balance,
                    adjusted_payoff=adjusted,
                )
            )
    return tuple(rows)
