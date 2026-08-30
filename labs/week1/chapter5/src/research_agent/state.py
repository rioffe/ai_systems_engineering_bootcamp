"""Explicit loop state and deterministic accounting."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def canonical_action(tool: str, arguments: dict[str, Any]) -> str:
    return canonical_json({"tool": tool, "arguments": arguments})


def surrogate_tokens(entry: Any) -> int:
    return math.ceil(len(canonical_json(entry)) / 4)


def surrogate_latency_ms(entry: Any) -> float:
    return (int(hashlib.sha256(canonical_json(entry).encode()).hexdigest()[:8], 16) % 1000) / 10.0


@dataclass
class AgentState:
    goal: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    step_count: int = 0
    tokens_used: int = 0
    cost_usd: float = 0.0
    consecutive_tool_failures: int = 0
    seen_actions: dict[str, int] = field(default_factory=dict)
    started_monotonic: float = 0.0

    def view(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("started_monotonic", None)
        return value

    def record(self, entry: dict[str, Any]) -> None:
        self.tokens_used += surrogate_tokens(entry)
        self.cost_usd = self.tokens_used * 0.000001
