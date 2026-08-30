# pyright: reportMissingImports=false

from decimal import Decimal

import pytest

from mortgage.amortization import amortize


def test_schedule_has_rows_and_zero_final_balance():
    rows = amortize(Decimal("1000"), Decimal("0"), 10, Decimal("100"))
    assert len(rows) == 10
    assert [row.period for row in rows] == list(range(1, 11))
    assert rows[-1].balance == Decimal("0")


def test_schedule_rejects_more_than_1200_payments():
    with pytest.raises(ValueError, match="INVALID_PAYMENTS"):
        amortize(Decimal("1000"), Decimal("0"), 1201, Decimal("1"))


def test_final_payoff_row_preserves_row_identity():
    rows = amortize(Decimal("100"), Decimal("0.1"), 3, Decimal("40"))
    final = rows[-1]
    assert final.adjusted_payoff is True
    assert final.payment == final.principal + final.interest
    assert final.balance == Decimal("0")
