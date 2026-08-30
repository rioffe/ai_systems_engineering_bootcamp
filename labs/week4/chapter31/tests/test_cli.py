# pyright: reportMissingImports=false

import json
import subprocess
import sys


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "mortgage.cli", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_calculate_command_returns_json_and_zero_exit():
    result = run_cli(
        "calculate", "--principal", "500000", "--rate", "6.5", "--term-years", "30", "--format", "json"
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["ok"] is True


def test_conflicting_term_flags_exit_two():
    result = run_cli(
        "calculate", "--principal", "100", "--rate", "0", "--payments", "10", "--term-years", "1"
    )
    assert result.returncode == 2


def test_eval_command_writes_report_and_passes(tmp_path):
    output = tmp_path / "eval-report.json"
    result = run_cli("eval", "--dataset", "evals/mortgage_questions.jsonl", "--out", str(output))
    assert result.returncode == 0
    report = json.loads(output.read_text())
    assert report["summary"] == {"total": 6, "passed": 6, "failed": 0}
    assert report["metrics"]["numeric_result_accuracy"] == 1.0


def test_eval_command_returns_one_for_failed_case(tmp_path):
    dataset = tmp_path / "bad.jsonl"
    dataset.write_text(json.dumps({
        "case_id": "wrong", "question": "What is the payment on a $100,000 mortgage at 5% for 30 years?",
        "expected": {"outcome": "calculated", "intent": "rate"},
    }) + "\n")
    result = run_cli("eval", "--dataset", str(dataset), "--out", str(tmp_path / "report.json"))
    assert result.returncode == 1
    assert "FAILED CASE: wrong" in result.stdout
    assert "What is the payment" in result.stdout
    assert "intent" in result.stdout


def test_mock_ask_is_offline():
    result = run_cli(
        "ask", "--adapter", "mock", "What is the payment on $500,000 at 6.5% for 30 years?"
    )
    assert result.returncode == 0
    assert "principal and interest" in result.stdout.lower()
