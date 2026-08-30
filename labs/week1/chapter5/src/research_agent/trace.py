"""Typed deterministic episode traces."""

from __future__ import annotations

import hashlib
from typing import Any

from .state import canonical_json


class TraceRecorder:
    def __init__(
        self, question: str, policy_id: str, budgets: dict[str, Any], fault_spec: str | None = None
    ):
        self.question, self.policy_id, self.budgets, self.fault_spec = (
            question,
            policy_id,
            budgets,
            fault_spec,
        )
        self.steps: list[dict[str, Any]] = []
        self.termination: dict[str, Any] = {}
        self.report: dict[str, Any] = {}

    @property
    def run_id(self) -> str:
        payload = [
            self.question,
            "fixture-v1",
            self.budgets,
            self.fault_spec,
            self.policy_id,
            "agent-prompt-v1",
        ]
        return hashlib.sha256(canonical_json(payload).encode()).hexdigest()[:12]

    def record_step(
        self, step: int, entries: list[dict[str, Any]], tokens: int = 0, cost_usd: float = 0.0
    ) -> None:
        self.steps.append(
            {"step": step, "entries": entries, "tokens": tokens, "cost_usd": round(cost_usd, 4)}
        )

    def record_termination(
        self, reason: str, steps: int, tokens: int, cost_usd: float, report: dict[str, Any]
    ) -> None:
        self.termination = {
            "reason": reason,
            "steps": steps,
            "tokens": tokens,
            "cost_usd": round(cost_usd, 4),
        }
        self.report = report

    def to_artifact(self) -> dict[str, Any]:
        return {
            "agent_trace_version": "0.1",
            "run_id": self.run_id,
            "question": self.question,
            "model": self.policy_id,
            "model_params": {},
            "prompt_version": "agent-prompt-v1",
            "usage_kind": "synthetic",
            "steps": self.steps,
            "termination": self.termination,
            "report": self.report,
            "loop_metrics": {},
        }
