"""Runtime-owned stopping conditions."""
from __future__ import annotations

from typing import Any

from .state import AgentState

REASONS = {"goal_complete", "max_steps", "token_budget", "cost_budget", "time_budget", "repeated_state", "consecutive_tool_failures"}

class BudgetEnforcer:
    def __init__(self, budgets: dict[str, Any]):
        self.budgets = budgets

    def check(self, state: AgentState) -> str | None:
        if state.seen_actions and max(state.seen_actions.values()) >= self.budgets["repeat_threshold"]:
            return "repeated_state"
        if state.step_count >= self.budgets["max_steps"]:
            return "max_steps"
        if state.tokens_used >= self.budgets["max_tokens"]:
            return "token_budget"
        if state.cost_usd >= self.budgets["max_cost_usd"]:
            return "cost_budget"
        if state.consecutive_tool_failures >= self.budgets["max_consecutive_failures"]:
            return "consecutive_tool_failures"
        return None
