# pyright: reportMissingImports=false
import json
from pathlib import Path

from research_agent.cli import main

ROOT = Path(__file__).parents[1]


def test_run_and_trace_commands(tmp_path, capsys):
    out = tmp_path / "trace.json"
    assert main(["run", "--question", "reimbursement limit", "--mock", "--out", str(out)]) == 0
    assert main(["trace", str(out)]) == 0
    assert "termination:" in capsys.readouterr().out


def test_drill_command_writes_report(tmp_path):
    out = tmp_path / "drill.json"
    assert main(["drill", "--name", "empty_results", "--out", str(out)]) == 0
    assert json.loads(out.read_text())["drill_report_version"] == "0.1"
