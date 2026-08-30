# pyright: reportMissingImports=false
from research_agent.budgets import BudgetEnforcer
from research_agent.state import AgentState


def test_repeated_state_precedes_max_steps():
    state = AgentState("q", step_count=10, seen_actions={'{"a":1}': 3})
    budgets = {"repeat_threshold": 3, "max_steps": 10, "max_tokens": 100, "max_cost_usd": 1, "max_consecutive_failures": 3}
    assert BudgetEnforcer(budgets).check(state) == "repeated_state"
