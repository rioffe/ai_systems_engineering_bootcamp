# pyright: reportMissingImports=false

import subprocess
import sys

from mortgage.llm import OllamaAdapter
from mortgage.diagnostics import configure_verbosity


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "mortgage.cli", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_verbose_logs_to_stderr_without_changing_result():
    normal = run_cli("calculate", "--principal", "120", "--rate", "0", "--term-years", "1")
    verbose = run_cli("--verbose", "calculate", "--principal", "120", "--rate", "0", "--term-years", "1")
    assert normal.returncode == verbose.returncode == 0
    assert normal.stdout == verbose.stdout
    assert "verbose" in verbose.stderr.lower()
    assert "periodic_rate" in verbose.stderr


def test_cli_verbose_is_accepted_after_subcommand():
    result = run_cli("calculate", "--verbose", "--principal", "120", "--rate", "0", "--term-years", "1")
    assert result.returncode == 0
    assert "verbose" in result.stderr.lower()


def test_info_metadata_excludes_raw_model_payloads():
    messages = []
    configure_verbosity("INFO", sink=messages.append)
    OllamaAdapter(model="llama3.2", chat_fn=lambda prompt: '{"principal": "1", "periodic_rate": "0", "payments": 1, "payment": null, "assumptions": [], "clarification": "missing", "evidence": []}').interpret("secret prompt")
    joined = "\n".join(messages)
    assert "MODEL PROMPT" not in joined
    assert "secret prompt" not in joined


def test_debug_includes_raw_model_payloads():
    messages = []
    configure_verbosity("DEBUG", sink=messages.append)
    OllamaAdapter(model="llama3.2", chat_fn=lambda prompt: '{"principal": "1", "periodic_rate": "0", "payments": 1, "payment": null, "assumptions": [], "clarification": "missing", "evidence": []}').interpret("secret prompt")
    joined = "\n".join(messages)
    assert "MODEL PROMPT" in joined
    assert "secret prompt" in joined
