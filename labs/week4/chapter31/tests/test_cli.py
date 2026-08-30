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


def test_mock_ask_is_offline():
    result = run_cli(
        "ask", "--adapter", "mock", "What is the payment on $500,000 at 6.5% for 30 years?"
    )
    assert result.returncode == 0
    assert "principal and interest" in result.stdout.lower()
