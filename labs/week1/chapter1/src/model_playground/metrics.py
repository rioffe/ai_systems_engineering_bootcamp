"""C-04 metrics (SPEC section 4 / C-04) -- pure, headless, deterministic.

Turns a run's raw wall-clock timings + token usage into TTFT / total latency /
TPS / cost. No I/O, no Qt, no network: the fast, always-run tests (T-03..T-06)
live here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .types import Usage

# Terminal run statuses (SPEC section 3.2 per-model state machine).
COMPLETED = "COMPLETED"
VALID = "VALID"
ERROR = "ERROR"
TIMED_OUT = "TIMED_OUT"
CANCELLED = "CANCELLED"

# Statuses that count as a "terminal success" for cost-per-task (SPEC C-04).
SUCCESS_STATUSES: frozenset[str] = frozenset({COMPLETED, VALID})


@dataclass(slots=True)
class RunMetrics:
    """All C-04 metrics for one model's run."""

    model_id: str
    status: str
    ttft_ms: float
    total_latency_ms: float
    tps: float
    usage: Usage
    cost_usd: float
    retries: int = 0
    error: str | None = None


def cost_usd(usage: Usage, price_input: float, price_output: float) -> float:
    """C-13 unit economics: N_in/1000 * P_in + N_out/1000 * P_out (I-006)."""
    return (
        usage.prompt_tokens / 1000.0 * price_input
        + usage.completion_tokens / 1000.0 * price_output
    )


def cost_per_success_task(total_cost: float, success_count: int) -> float:
    """Derived aggregate (SPEC C-04 / section 13, I-007).

    total cost across a run divided by the number of models that reached a
    terminal success state. The denominator is clamped to at least 1 so an
    all-failed run yields the raw total rather than a division by zero.
    """
    denom = success_count if success_count > 0 else 1
    return total_cost / denom


def compute_metrics(
    model_id: str,
    *,
    t_request: float,
    t_first_token: float | None,
    t_complete: float,
    usage: Usage,
    price_input: float,
    price_output: float,
    retries: int = 0,
    status: str = COMPLETED,
    error: str | None = None,
) -> RunMetrics:
    """Compute C-04 metrics; invariants I-004/I-005 are enforced by construction.

    Timings are monotonic seconds. For a non-streaming run (or an empty response)
    t_first_token is None, in which case TTFT is defined to equal the total
    latency (the E-04 special case), which also guards TPS at 0.0 (I-005) because
    the generation interval is then zero.
    """
    total_s = max(0.0, t_complete - t_request)
    if t_first_token is None:
        ttft_s = total_s
    else:
        ttft_s = max(0.0, t_first_token - t_request)
    ttft_s = min(ttft_s, total_s)

    generation_s = total_s - ttft_s
    if generation_s > 0.0 and usage.completion_tokens > 0:
        tps = usage.completion_tokens / generation_s
    else:
        tps = 0.0
    if not math.isfinite(tps):
        tps = 0.0

    return RunMetrics(
        model_id=model_id,
        status=status,
        ttft_ms=ttft_s * 1000.0,
        total_latency_ms=total_s * 1000.0,
        tps=tps,
        usage=usage,
        cost_usd=cost_usd(usage, price_input, price_output),
        retries=retries,
        error=error,
    )


__all__ = [
    "CANCELLED",
    "COMPLETED",
    "ERROR",
    "SUCCESS_STATUSES",
    "TIMED_OUT",
    "VALID",
    "RunMetrics",
    "compute_metrics",
    "cost_per_success_task",
    "cost_usd",
]
