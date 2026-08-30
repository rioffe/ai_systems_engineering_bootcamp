# pyright: reportMissingImports=false

from decimal import Decimal

from mortgage.models import CalculationRequest
from mortgage.validation import validate_request


def test_accepts_exactly_three_canonical_values():
    request = CalculationRequest(Decimal("500000"), Decimal("0.005"), 360, None)
    assert validate_request(request) is None


def test_rejects_wrong_quantity_count():
    request = CalculationRequest(Decimal("500000"), None, None, None)
    assert validate_request(request).code == "INVALID_QUANTITY_COUNT"


def test_rejects_non_integral_term():
    request = CalculationRequest(Decimal("100"), Decimal("0"), None, Decimal("30"))
    error = validate_request(request, missing="payments", integer_candidate=Decimal("3.333"))
    assert error.code == "INVALID_PAYMENTS"
    assert error.details["reason"] == "NON_INTEGRAL_TERM"
