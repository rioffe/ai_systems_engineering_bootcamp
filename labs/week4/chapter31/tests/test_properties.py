# pyright: reportMissingImports=false

from decimal import Decimal

from hypothesis import given, settings, strategies as st

from mortgage.calculator import calculate_payment, calculate_principal, calculate_rate


@settings(max_examples=100, derandomize=True)
@given(
    principal=st.integers(min_value=1_000, max_value=100_000),
    rate_basis_points=st.integers(min_value=1, max_value=20),
    payments=st.integers(min_value=12, max_value=120),
)
def test_payment_principal_round_trip(principal, rate_basis_points, payments):
    principal = Decimal(principal)
    periodic_rate = Decimal(rate_basis_points) / Decimal("10000")
    payment = calculate_payment(principal, periodic_rate, payments)
    recovered = calculate_principal(payment, periodic_rate, payments)
    assert abs(recovered - principal) < Decimal("1e-30")


@settings(max_examples=100, derandomize=True)
@given(
    principal=st.integers(min_value=1_000, max_value=100_000),
    rate_basis_points=st.integers(min_value=1, max_value=20),
    payments=st.integers(min_value=12, max_value=120),
)
def test_payment_rate_round_trip(principal, rate_basis_points, payments):
    principal = Decimal(principal)
    periodic_rate = Decimal(rate_basis_points) / Decimal("10000")
    payment = calculate_payment(principal, periodic_rate, payments)
    recovered = calculate_rate(
        principal, payment, payments, tolerance=Decimal("1e-12"), max_iterations=100
    )
    assert abs(recovered - periodic_rate) < Decimal("1e-10")
