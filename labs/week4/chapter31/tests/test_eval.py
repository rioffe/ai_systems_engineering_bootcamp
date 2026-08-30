# pyright: reportMissingImports=false

import json
from decimal import Decimal

import pytest

from mortgage.eval import evaluate_cases, load_cases, write_report
from mortgage.llm import MockLLMAdapter


def _case(case_id, question, expected):
    return {"case_id": case_id, "category": "test", "question": question, "expected": expected}


def test_load_cases_requires_expected_contract(tmp_path):
    path = tmp_path / "cases.jsonl"
    path.write_text(json.dumps({"case_id": "missing", "question": "x"}) + "\n")
    with pytest.raises(ValueError, match="expected"):
        load_cases(path)


def test_mock_eval_scores_calculated_payment():
    cases = [
        _case(
            "payment-basic",
            "What is the payment on a $100,000 mortgage at 5% for 30 years?",
            {
                "intent": "payment",
                "outcome": "calculated",
                "fields": {"principal": "100000", "payments": 360},
                "result": {"payment": "536.821623012139", "tolerance": "0.01"},
            },
        )
    ]
    report = evaluate_cases(cases, MockLLMAdapter(), adapter_name="mock", model_name=None)
    assert report["summary"] == {"total": 1, "passed": 1, "failed": 0}
    assert report["metrics"]["numeric_result_accuracy"] == 1.0
    assert report["cases"][0]["status"] == "PASS"
    assert report["cases"][0]["failure_reasons"] == []


def test_mock_eval_scores_clarification_and_scope():
    cases = [
        _case("clarify", "How much would a $500,000 mortgage cost?", {"outcome": "clarification"}),
        _case("scope", "What will taxes and insurance add?", {"outcome": "unsupported_scope"}),
    ]
    report = evaluate_cases(cases, MockLLMAdapter(), adapter_name="mock", model_name=None)
    assert report["summary"] == {"total": 2, "passed": 2, "failed": 0}
    assert report["metrics"]["clarification_accuracy"] == 1.0
    assert report["metrics"]["scope_accuracy"] == 1.0


def test_failed_case_contains_detailed_reasons():
    cases = [_case("wrong", "What is the payment on a $100,000 mortgage at 5% for 30 years?", {
        "intent": "rate", "outcome": "calculated",
        "fields": {"principal": "100000"},
        "result": {"payment": "1", "tolerance": "0.01"},
    })]
    report = evaluate_cases(cases, MockLLMAdapter(), adapter_name="mock", model_name=None)
    row = report["cases"][0]
    assert row["status"] == "FAIL"
    assert row["failure_classification"] == "intent_mismatch"
    assert "intent" in row["failure_reasons"]
    assert "numeric_result.payment" in row["failure_reasons"]


def test_write_report_is_sorted_and_versioned(tmp_path):
    path = tmp_path / "report.json"
    write_report(path, {"summary": {"total": 0, "passed": 0, "failed": 0}, "cases": []})
    data = json.loads(path.read_text())
    assert data["eval_version"] == "0.1"
    assert path.read_text().endswith("\n")
