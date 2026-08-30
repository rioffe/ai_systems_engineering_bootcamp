"""Bounded deterministic runtime loop."""

from __future__ import annotations

from typing import Any

from .authorize import AuthorizationEngine
from .budgets import BudgetEnforcer
from .metrics import compute_loop_metrics
from .retry import execute_with_retry
from .state import AgentState, canonical_action
from .trace import TraceRecorder
from .validate import validate_decision, validate_final_report


class AgentRuntime:
    def __init__(
        self,
        policy: Any,
        tools: Any,
        budgets: dict[str, Any],
        authorization: AuthorizationEngine | None = None,
        recorder: TraceRecorder | None = None,
    ):
        self.policy, self.tools, self.budgets = policy, tools, budgets
        self.authorization = authorization or AuthorizationEngine(
            {
                "rules": [
                    {"tool": "search", "effect": "allow"},
                    {"tool": "retrieve", "effect": "allow"},
                ],
                "default": "deny",
            }
        )
        self.recorder = recorder

    def run(self, question: str) -> dict[str, Any]:
        state = AgentState(question)
        recorder = self.recorder or TraceRecorder(question, "mock-policy", self.budgets)
        report: dict[str, Any] = {
            "status": "insufficient_evidence",
            "answer": "The requested information could not be verified from the available sources.",
            "citations": [],
            "conflicts": [],
            "caveats": [],
        }
        reason = "max_steps"
        for _ in range(self.budgets["max_steps"] + 1):
            stop = BudgetEnforcer(self.budgets).check(state)
            if stop:
                reason = stop
                break
            decision = self.policy.decide(state.view(), list(self.tools.specs))
            errors = validate_decision(decision, self.tools)
            if errors:
                observation = {
                    "kind": "observation",
                    "error": "invalid_arguments",
                    "field": errors[0]["field"],
                    "message": errors[0]["message"],
                }
                state.observations.append(observation)
                state.record(observation)
                recorder.record_step(
                    state.step_count,
                    [{"kind": "reasoning", "text": "repairing invalid arguments"}, observation],
                    state.tokens_used,
                    state.cost_usd,
                )
                state.step_count += 1
                continue
            if decision["type"] == "final":
                retrieved = {
                    o["result"]["doc_id"]
                    for o in state.observations
                    if o.get("result") and isinstance(o["result"], dict) and "doc_id" in o["result"]
                }
                errors = validate_final_report(decision["report"], retrieved)
                if not errors:
                    report = decision["report"]
                    reason = "goal_complete"
                    break
                observation = {
                    "kind": "observation",
                    "error": "invalid_report",
                    "field": errors[0]["field"],
                    "message": errors[0]["message"],
                }
                state.observations.append(observation)
                state.record(observation)
                state.step_count += 1
                recorder.record_step(
                    state.step_count - 1, [observation], state.tokens_used, state.cost_usd
                )
                continue
            tool, arguments = decision["tool"], decision["arguments"]
            action_key = canonical_action(tool, arguments)
            state.seen_actions[action_key] = state.seen_actions.get(action_key, 0) + 1
            auth = self.authorization.authorize(tool, arguments)
            entries = [
                {
                    "kind": "reasoning",
                    "text": "searching for evidence" if tool == "search" else "retrieving top hit",
                },
                {"kind": "action", "tool": tool, "arguments": arguments},
            ]
            if not auth.allowed:
                observation = {
                    "kind": "observation",
                    "tool": tool,
                    "error": "permission_denied",
                    "result": None,
                    "attempt": 1,
                }
                state.observations.append(observation)
                state.record(observation)
                state.step_count += 1
                recorder.record_step(
                    state.step_count - 1, entries + [observation], state.tokens_used, state.cost_usd
                )
                continue
            call = self.tools.search if tool == "search" else self.tools.retrieve
            value = arguments.get("query") if tool == "search" else arguments.get("document_id")
            execution = execute_with_retry(
                lambda selected_call=call, selected_value=value: selected_call(selected_value),
                self.budgets["max_retries"],
            )
            observation = {
                "kind": "observation",
                "tool": tool,
                "result": execution.result,
                "error": execution.error,
                "attempt": execution.attempts,
            }
            state.observations.append(observation)
            state.record(observation)
            state.step_count += 1
            state.consecutive_tool_failures = (
                state.consecutive_tool_failures + 1 if execution.error else 0
            )
            recorder.record_step(
                state.step_count - 1, entries + [observation], state.tokens_used, state.cost_usd
            )
        recorder.record_termination(
            reason, state.step_count, state.tokens_used, state.cost_usd, report
        )
        artifact = recorder.to_artifact()
        artifact["loop_metrics"] = compute_loop_metrics(artifact)
        return artifact
