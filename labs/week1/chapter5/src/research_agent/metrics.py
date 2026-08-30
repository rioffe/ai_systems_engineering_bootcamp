"""Pure loop metrics over parsed traces."""
from __future__ import annotations

from collections import Counter
from typing import Any

LOOP_METRIC_KEYS = ["steps_used", "tool_calls", "search_calls", "retrieve_calls", "invalid_argument_count", "repair_success", "retry_count", "denial_count", "unnecessary_call_estimate", "termination_reason", "latency_ms", "tokens_total", "cost_usd_total"]


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def compute_loop_metrics(trace: dict[str, Any]) -> dict[str, Any]:
    entries = [entry for step in trace.get("steps", []) for entry in step.get("entries", [])]
    actions = [entry for entry in entries if entry.get("kind") == "action"]
    observations = [entry for entry in entries if entry.get("kind") == "observation"]
    counts = Counter((a.get("tool"), str(a.get("arguments"))) for a in actions)
    invalid = [o for o in observations if o.get("error") == "invalid_arguments"]
    repaired = sum(any(a.get("tool") == invalid_entry.get("tool") for a in actions[index + 1:]) for index, invalid_entry in enumerate(observations) if invalid_entry.get("error") == "invalid_arguments")
    return {"steps_used": len(trace.get("steps", [])), "tool_calls": len(actions), "search_calls": sum(a.get("tool") == "search" for a in actions), "retrieve_calls": sum(a.get("tool") == "retrieve" for a in actions), "invalid_argument_count": len(invalid), "repair_success": repaired / len(invalid) if invalid else 1.0, "retry_count": sum(max(0, _int(o.get("attempt", 1)) - 1) for o in observations), "denial_count": sum(o.get("error") == "permission_denied" for o in observations), "unnecessary_call_estimate": sum(count - 1 for count in counts.values() if count > 1), "termination_reason": trace.get("termination", {}).get("reason"), "latency_ms": trace.get("termination", {}).get("latency_ms", 0.0), "tokens_total": trace.get("termination", {}).get("tokens", 0), "cost_usd_total": trace.get("termination", {}).get("cost_usd", 0.0)}
