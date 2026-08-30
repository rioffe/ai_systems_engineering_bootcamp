# pyright: reportMissingImports=false

from decimal import Decimal

import pytest

from mortgage.calculator import (
    MortgageCalculator,
    calculate_payment,
    calculate_rate,
)
from mortgage.models import CalculationRequest


def test_known_payment_value():
    actual = calculate_payment(Decimal("100000"), Decimal("0.06") / 12, 360)
    assert abs(actual - Decimal("599.550525152752")) < Decimal("1e-9")


def test_zero_rate_payment_and_principal():
    result = MortgageCalculator().calculate(
        CalculationRequest(Decimal("120"), Decimal("0"), 12, None)
    )
    assert result.payment == Decimal("10")


def test_zero_rate_principal_from_payment():
    result = MortgageCalculator().calculate(
        CalculationRequest(Decimal("120"), Decimal("0"), None, Decimal("10"))
    )
    assert result.payments == 12


def test_payment_count_ceil_preserves_exact_fractional_term():
    result = MortgageCalculator().calculate(
        CalculationRequest(Decimal("500000"), Decimal("0.005"), None, Decimal("3000"))
    )
    assert result.payments == 360
    assert result.exact_payments == Decimal("359.24702887430622966044602613653870430753476453958")
    assert result.exact_term_years == Decimal("29.937252406192185805037168844711558692294563711632")


def test_rate_round_trip_uses_bisection():
    payment = calculate_payment(Decimal("100000"), Decimal("0.005"), 360)
    actual = calculate_rate(Decimal("100000"), payment, 360, tolerance=Decimal("1e-12"), max_iterations=100)
    assert abs(actual - Decimal("0.005")) < Decimal("1e-10")


def test_rate_solver_rejects_unbracketed_payment():
    with pytest.raises(ValueError, match="SOLVER_CONVERGENCE"):
        calculate_rate(Decimal("100000"), Decimal("1"), 360, tolerance=Decimal("1e-12"), max_iterations=100)
