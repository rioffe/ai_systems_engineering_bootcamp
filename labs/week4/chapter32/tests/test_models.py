# pyright: reportMissingImports=false
from decimal import Decimal

from synthgen.models import GenerationResult, GroundTruth, Realization, Scenario


def test_contracts_are_frozen_and_preserve_decimal_values():
    scenario = Scenario("payment-000001", "payment", {"principal": Decimal("100")}, "calculated", 0)
    truth = GroundTruth("calculated", {"payment": Decimal("1")}, "mortgage", "chapter31")
    realization = Realization("What is the payment?", "template", "payment_01", None, None)
    assert scenario.fields["principal"] == Decimal("100")
    assert truth.source == "mortgage"
    assert realization.raw_response is None


def test_publication_result_exposes_records_report_manifest_and_failures():
    result = GenerationResult(records=(), report={}, manifest={}, failures=())
    assert result.records == ()
