# pyright: reportMissingImports=false

from decimal import Decimal

from mortgage.llm import MockLLMAdapter


def test_mock_payment_question_calls_tool_once():
    adapter = MockLLMAdapter()
    response = adapter.ask("What is the payment on a $500,000 mortgage at 6.5% for 30 years?")
    assert response.ok is True
    assert Decimal(response.result["payment"]) > 0
    assert all(e.origin == "explicit" for e in response.interpretation.evidence)
    assert adapter.tool_calls == 1


def test_underspecified_question_requests_clarification():
    response = MockLLMAdapter().ask("How much would a $500,000 mortgage cost?")
    assert response.interpretation.clarification
    assert response.result is None


def test_scope_question_is_rejected_without_arithmetic():
    response = MockLLMAdapter().ask("What will taxes and insurance add?")
    assert response.error["code"] == "UNSUPPORTED_SCOPE"


def test_derived_down_payment_has_evidence_and_assumption():
    response = MockLLMAdapter().ask(
        "I want a $600,000 house with 20% down at 6.25% for 30 years."
    )
    assert response.ok is True
    principal = next(e for e in response.interpretation.evidence if e.field == "principal")
    assert principal.origin == "derived"
    assert response.interpretation.assumptions
