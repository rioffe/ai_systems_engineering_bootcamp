# pyright: reportMissingImports=false
from pathlib import Path

from research_agent.config import load_budgets
from research_agent.policy import MockPolicy
from research_agent.runtime import AgentRuntime
from research_agent.tools import build_registry

ROOT = Path(__file__).parents[1]


def test_runtime_completes_bounded_episode():
    artifact = AgentRuntime(MockPolicy(), build_registry(ROOT / "corpus"), load_budgets()).run("reimbursement limit")
    assert artifact["termination"]["reason"] == "goal_complete"
    assert artifact["report"]["status"] == "ok"
    assert len(artifact["steps"]) == 2


def test_never_final_hits_max_steps():
    budgets = {**load_budgets(), "max_steps": 3}
    artifact = AgentRuntime(MockPolicy("never_final"), build_registry(ROOT / "corpus"), budgets).run("q")
    assert artifact["termination"]["reason"] == "max_steps"
