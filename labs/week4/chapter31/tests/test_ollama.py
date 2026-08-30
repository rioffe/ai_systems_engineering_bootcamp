# pyright: reportMissingImports=false

import json
from decimal import Decimal

import pytest

from mortgage.llm import OllamaAdapter, OllamaClient


def test_ollama_client_rejects_non_http_hosts():
    with pytest.raises(ValueError, match="http or https"):
        OllamaClient(host="file:///tmp/models")


def test_ollama_client_lists_local_models(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"models": [{"name": "llama3.2:latest"}, {"name": "phi4-mini:latest"}]}).encode()

    monkeypatch.setattr("mortgage.llm.urlopen", lambda request, timeout: FakeResponse())
    assert OllamaClient(host="http://localhost:11434").list_models() == [
        "llama3.2:latest", "phi4-mini:latest"
    ]


def test_ollama_adapter_uses_structured_interpretation_and_calculator():
    calls = []

    def fake_chat(prompt):
        calls.append(prompt)
        if len(calls) == 1:
            return json.dumps(
                {
                    "principal": "500000",
                    "periodic_rate": "0.005416666666666666666666666667",
                    "payments": 360,
                    "payment": None,
                    "assumptions": [],
                    "clarification": None,
                    "evidence": [
                        {"field": "principal", "source_text": "$500,000", "normalized_value": "500000", "origin": "explicit"},
                        {"field": "periodic_rate", "source_text": "6.5%", "normalized_value": "0.005416666666666666666666666667", "origin": "explicit"},
                        {"field": "payments", "source_text": "30 years", "normalized_value": "360", "origin": "explicit"},
                    ],
                }
            )
        return "The validated principal-and-interest payment is $3,160.34 per month."

    response = OllamaAdapter(model="llama3.2", chat_fn=fake_chat).ask(
        "What is the payment on a $500,000 mortgage at 6.5% for 30 years?"
    )
    assert response.ok is True
    assert response.result["payment"]
    assert len(calls) == 2
    assert "calculator result" in calls[1].lower()
    assert "not interest-only" in calls[1].lower()


def test_ollama_adapter_accepts_json_code_fence():
    payload = {
        "principal": "100000",
        "periodic_rate": "0.004166666666666666666666666667",
        "payments": 360,
        "payment": None,
        "assumptions": [],
        "clarification": None,
        "evidence": [],
    }
    fenced = f"```json\n{json.dumps(payload)}\n```".replace(" ", "\u2581")
    adapter = OllamaAdapter(model="gemma3n:e4b", chat_fn=lambda _: fenced)
    interpretation = adapter.interpret("What is the payment on a $100,000 loan at 5% for 30 years?")
    assert interpretation.request is not None
    assert interpretation.request.principal == 100000
    assert interpretation.request.payment is None


def test_ollama_adapter_canonicalizes_gemma_aliases_for_payment_question():
    response_json = {
        "loan_amount": "100000",
        "interest_rate": "0.05",
        "loan_term": "30",
        "payment": "197.07",
        "assumptions": [],
        "clarification": None,
        "evidence": [],
    }
    adapter = OllamaAdapter(
        model="gemma3n:e4b",
        chat_fn=lambda prompt: json.dumps(response_json) if "Extract" in prompt else "ok",
    )
    response = adapter.ask("What's the payment on a 5% a year $100,000 30-year loan?")
    assert response.ok is True
    assert response.result["payments"] == 360
    assert response.result["payment"] != "197.07"


def test_ollama_adapter_normalizes_tokenized_spaces_in_explanation():
    payload = {
        "principal": "100000",
        "periodic_rate": "0.004166666666666666666666666667",
        "payments": 360,
        "payment": None,
        "assumptions": [],
        "clarification": None,
        "evidence": [],
    }
    calls = 0

    def fake_chat(prompt):
        nonlocal calls
        calls += 1
        return json.dumps(payload) if calls == 1 else "The payment is $536.82.▁▁"

    response = OllamaAdapter(model="gemma3n:e4b", chat_fn=fake_chat).ask("payment")
    assert response.explanation == "The payment is $536.82.  "


def test_ollama_adapter_replaces_contradictory_explanation():
    payload = {
        "principal": "100000",
        "periodic_rate": "0.004166666666666666666666666667",
        "payments": 360,
        "payment": None,
        "assumptions": [],
        "clarification": None,
        "evidence": [],
    }
    calls = 0

    def fake_chat(prompt):
        nonlocal calls
        calls += 1
        return json.dumps(payload) if calls == 1 else "This does not account for interest compounding."

    response = OllamaAdapter(model="llama3.2", chat_fn=fake_chat).ask("payment")
    assert response.explanation == "The calculator determined a fixed principal-and-interest payment of $536.82 per month."


def test_ollama_adapter_explains_solved_rate_not_payment():
    payload = {
        "principal": "100000",
        "periodic_rate": None,
        "payments": 360,
        "payment": "500",
        "assumptions": [],
        "clarification": None,
        "evidence": [],
    }
    calls = 0

    def fake_chat(prompt):
        nonlocal calls
        calls += 1
        return json.dumps(payload) if calls == 1 else "The payment is $500.00 per month."

    response = OllamaAdapter(model="gemma3n:e4b", chat_fn=fake_chat).ask("what yearly interest rate?")
    assert response.ok is True
    assert "annual interest rate" in response.explanation.lower()
    assert "payment is $500.00" not in response.explanation.lower()


def test_ollama_adapter_uses_annual_rate_evidence_and_ignores_generic_clarification():
    response_text = '''```\n{
      "principal": "100000",
      "periodic_rate": "0.041667",
      "payments": "360",
      "payment": "null",
      "assumptions": "null",
      "clarification": "Missing calculation",
      "evidence": [
        {"field": "Interest Rate", "source_text": "5% per annum", "normalized_value": "0.05", "origin": "Annual"},
        {"field": "Loan Term (years)", "source_text": "30 years", "normalized_value": "30", "origin": "Number of years"}
      ]
    }
```'''
    adapter = OllamaAdapter(model="llama3.2:latest", chat_fn=lambda prompt: response_text)
    interpretation = adapter.interpret("What is the payment on a 5% a year $100,000 30-year loan?")
    assert interpretation.clarification is None
    assert interpretation.request is not None
    assert interpretation.request.periodic_rate == Decimal("0.05") / Decimal(12)
    assert interpretation.request.payment is None


def test_ollama_adapter_uses_explicit_user_units_when_model_omits_term():
    response_text = json.dumps(
        {
            "principal": "100000",
            "periodic_rate": "0.041667",
            "payments": None,
            "payment": None,
            "assumptions": None,
            "clarification": "Missing information",
            "evidence": [],
        }
    )
    adapter = OllamaAdapter(model="llama3.2:latest", chat_fn=lambda _: response_text)
    interpretation = adapter.interpret("What is the payment on a 5% a year $100,000 30-year loan?")
    assert interpretation.request is not None
    assert interpretation.request.periodic_rate == Decimal("0.05") / Decimal(12)
    assert interpretation.request.payments == 360


def test_ollama_adapter_overrides_phi4_missing_input_clarification():
    response_text = json.dumps(
        {
            "principal": "100000",
            "periodic_rate": None,
            "payments": None,
            "payment": None,
            "assumptions": None,
            "clarification": "The periodic_rate (monthly interest rate) is required to calculate the payment amount.",
            "evidence": [
                {"field": "periodic_rate", "source_text": None, "normalized_value": None, "origin": None},
                {"field": "payments", "source_text": None, "normalized_value": None, "origin": None},
                {"field": "payment", "source_text": None, "normalized_value": None, "origin": None},
            ],
        }
    )
    adapter = OllamaAdapter(model="phi4-mini:latest", chat_fn=lambda _: response_text)
    response = adapter.ask("What is the payment on a 5% a year $100,000 30-year loan?")
    assert response.ok is True
    assert response.result["payments"] == 360
    assert response.result["payment"] != "null"


def test_ollama_adapter_recognizes_yearly_rate_intent_with_monthly_payment():
    response_text = json.dumps(
        {
            "principal": "100000",
            "periodic_rate": "0.004166666666666667",
            "payments": "12",
            "payment": "500",
            "assumptions": None,
            "clarification": "null",
            "evidence": [],
        }
    )
    adapter = OllamaAdapter(model="gemma3n:e4b", chat_fn=lambda prompt: response_text)
    response = adapter.ask(
        "What is the yearly interest rate if I pay $500 per month on a $100,000 30-year loan?"
    )
    assert response.ok is True
    assert response.result["payments"] == 360
    assert response.result["periodic_rate"] != "0.004166666666666667"


def test_ollama_adapter_extracts_json_after_prose_and_recovers_payment():
    response_text = '''Here is the JSON response:

```
{
  "principal": 100000,
  "periodic_rate": null,
  "payments": 500,
  "payment": null,
  "assumptions": null,
  "clarification": "The periodic_rate (monthly interest rate) is required.",
  "evidence": [
    {"field": "monthly payment", "source_text": "pay $500 per month", "normalized_value": "500", "origin": "Given information"},
    {"field": "loan term", "source_text": "30-year loan", "normalized_value": "30", "origin": "Given information"}
  ]
}
```'''
    adapter = OllamaAdapter(model="llama3.2", chat_fn=lambda _: response_text)
    response = adapter.ask(
        "What is the yearly interest rate if I pay $500 per month on a $100,000 30-year loan?"
    )
    assert response.ok is True
    assert response.result["payments"] == 360
    assert response.result["payment"] == "500"
    assert response.result["periodic_rate"] != "0.004166666666666667"


def test_ollama_adapter_converts_malformed_model_output_to_model_error():
    response = OllamaAdapter(model="llama3.2", chat_fn=lambda _: "not json").ask("calculate this")
    assert response.ok is False
    assert response.error["code"] == "MODEL_ERROR"
