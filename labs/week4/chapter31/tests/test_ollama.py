# pyright: reportMissingImports=false

import json

from mortgage.llm import OllamaAdapter


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


def test_ollama_adapter_converts_malformed_model_output_to_model_error():
    response = OllamaAdapter(model="llama3.2", chat_fn=lambda _: "not json").ask("calculate this")
    assert response.ok is False
    assert response.error["code"] == "MODEL_ERROR"
