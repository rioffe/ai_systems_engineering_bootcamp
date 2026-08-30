# pyright: reportMissingImports=false
from pathlib import Path

from research_agent.config import load_budgets
from research_agent.policy import MockPolicy
from research_agent.report import write_trace
from research_agent.runtime import AgentRuntime
from research_agent.tools import build_registry

ROOT = Path(__file__).parents[1]


def test_repeated_mock_runs_are_byte_identical(tmp_path):
    budgets = load_budgets()
    first = AgentRuntime(MockPolicy(), build_registry(ROOT / "corpus"), budgets).run("reimbursement limit")
    second = AgentRuntime(MockPolicy(), build_registry(ROOT / "corpus"), budgets).run("reimbursement limit")
    left, right = tmp_path / "a.json", tmp_path / "b.json"
    write_trace(left, first)
    write_trace(right, second)
    assert left.read_bytes() == right.read_bytes()
