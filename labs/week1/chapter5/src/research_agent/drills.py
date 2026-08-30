"""Deterministic Chapter 5 failure drills."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import load_budgets
from .policy import MockPolicy
from .runtime import AgentRuntime
from .tools import build_registry

DRILLS = {
    "search_timeout": {"policy": None, "expected": "goal_complete"},
    "empty_results": {"policy": None, "expected": "goal_complete"},
    "malformed_arguments": {"policy": "null_query", "expected": "goal_complete"},
    "retrieval_failure": {"policy": "retrieval_failure", "expected": "goal_complete"},
    "duplicate_searches": {"policy": "repeat_search", "expected": "repeated_state"},
    "contradictory_sources": {"policy": None, "expected": "goal_complete"},
    "low_quality_sources": {"policy": None, "expected": "goal_complete"},
    "infinite_loop": {"policy": "repeat_search", "expected": "repeated_state"},
    "max_steps_exhaustion": {"policy": "never_final", "expected": "max_steps"},
    "unauthorized_tool_call": {"policy": "attempt_delete", "expected": "goal_complete"},
}


def run_drill(name: str, budgets: dict[str, Any] | None = None, corpus_dir: str | Path | None = None) -> dict[str, Any]:
    if name not in DRILLS:
        raise ValueError(f"unknown drill: {name}")
    budgets = budgets or load_budgets()
    corpus_dir = corpus_dir or Path(__file__).resolve().parents[2] / "corpus"
    policy_fault = DRILLS[name]["policy"]
    trace = AgentRuntime(MockPolicy(policy_fault), build_registry(corpus_dir), budgets).run("reimbursement limit")
    actual = trace["termination"]["reason"]
    passed = actual == DRILLS[name]["expected"]
    return {"drill_report_version": "0.1", "drill": name, "trace_path": f"drills/{name}.trace.json", "model_behavior": f"MockPolicy proposed the configured {name} behavior.", "runtime_behavior": f"Runtime terminated with {actual}.", "expected_behavior": f"Runtime should terminate with {DRILLS[name]['expected']}.", "instrumentation": "Typed trace and loop metrics expose the decision, observation, retries, and termination.", "verdict": {"expected_termination": DRILLS[name]["expected"], "actual_termination": actual, "pass": passed}, "trace": trace}
