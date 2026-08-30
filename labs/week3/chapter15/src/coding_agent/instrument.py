# C-06 / F-013 / K-07 / I-010 / I-002: trajectory instrumentation.
#
# `instrument.py` is IN the I-009 LLM/network-free core list (stdlib only). It
# builds the per-iteration rows of `trajectory.json` (C-06) and the envelope,
# applying the pinned conventions:
#
#   * F-001 -- iterations are 1-based.
#   * F-008 -- `phase` is one of the 8-value pinned vocabulary.
#   * F-013 -- `files_read` / `files_modified` are DISTINCT (first-seen order);
#     only `read_file` increments files_read and only an *applied* edit_file
#     increments files_modified (the caller passes in only applied paths).
#   * K-07  -- on the mock path, tokens.estimated = len(C_t chars) + 4*len
#     (tool_calls) and time_ms = 5*iteration + 10*len(tool_calls), labeled
#     "synthetic"; wall-clock is never reported there (E-04).
#   * I-010 -- every row carries exactly the C-06 field set.
#   * I-002 -- the document is a pure function of its inputs, so identical runs
#     serialize byte-identically (report.py pins the serialization form).

from __future__ import annotations

# F-008: the pinned phase vocabulary for the C-06 `phase` field.
PHASES = ("observe", "inspect", "search", "propose", "modify", "verify", "repair", "stop")

# C-08: the terminal-stopping outcomes `final_outcome` may take (F-014 win-rule).
TERMINAL_OUTCOMES = (
    "VERIFIED",
    "BUDGET_EXHAUSTED",
    "STALLED:NOOP",
    "STALLED:BUDGET",
    "DENIED_LOOP",
    "ERROR",
)

SYNTHETIC = "synthetic"  # K-07 label for mock surrogate counters (E-04).
MEASURED = "measured"  # the real-Ollama path labels real counters this way.


# K-07: tokens.estimated = len(C_t chars) + 4 * len(tool_calls) (normative).
def surrogate_tokens(context_chars: int, n_calls: int) -> int:
    return context_chars + 4 * n_calls


# K-07: time_ms = 5 * iteration + len(tool_calls) * 10 (normative, 1-based index).
def surrogate_time_ms(iteration: int, n_calls: int) -> int:
    return 5 * iteration + 10 * n_calls


def _distinct(paths: list[str]) -> list[str]:
    # F-013: distinct paths, first-seen order preserved.
    seen: list[str] = []
    for p in paths:
        if p not in seen:
            seen.append(p)
    return seen


# Build one C-06 iteration row (I-010 field totality). The caller passes the
# raw iteration facts; this applies the counting and surrogate rules.
def build_row(
    *,
    iteration: int,
    tool_calls: list[dict],
    context_chars: int,
    files_read: list[str] | None = None,
    files_modified: list[str] | None = None,
    tests_executed: int = 0,
    test_results: dict | None = None,
    errors: list[str] | None = None,
    verdict: str = "PENDING",
    phase: str = "observe",
    mode: str = SYNTHETIC,
    time_ms: int | None = None,
) -> dict:
    if iteration < 1:
        raise ValueError(f"iteration is 1-based (F-001); got {iteration}")
    if phase not in PHASES:
        raise ValueError(f"phase {phase!r} not in the pinned vocabulary (F-008)")
    if verdict not in ("PENDING", "VERIFIED", "FAILED", "ERROR"):
        raise ValueError(f"verdict {verdict!r} not in {{PENDING, VERIFIED, FAILED, ERROR}}")
    n_calls = len(tool_calls)
    return {
        "iteration": iteration,
        "tool_calls": list(tool_calls),
        "tokens": {"estimated": surrogate_tokens(context_chars, n_calls), "mode": mode},
        "files_read": _distinct(list(files_read or [])),
        "files_modified": _distinct(list(files_modified or [])),
        "tests_executed": tests_executed,
        "test_results": test_results,
        "errors": list(errors or []),
        "time_ms": surrogate_time_ms(iteration, n_calls) if time_ms is None else time_ms,
        "verdict": verdict,
        "phase": phase,
    }


# Accumulates iteration rows and finalizes the C-06 envelope.
class Trajectory:
    def __init__(
        self,
        *,
        task_id: str,
        policy: str,
        sandbox_root: str,
        availability_banner: str | None = None,
    ) -> None:
        self.task_id = task_id
        self.policy = policy
        self.sandbox_root = sandbox_root
        self.availability_banner = availability_banner
        self.rows: list[dict] = []

    def add_row(self, row: dict) -> None:
        self.rows.append(row)

    def finalize(self, final_outcome: str) -> dict:
        # F-014: final_outcome is the terminal-stopping label, not the last verdict.
        if final_outcome not in TERMINAL_OUTCOMES:
            raise ValueError(f"final_outcome {final_outcome!r} not in {TERMINAL_OUTCOMES} (C-08)")
        mode = self.rows[0]["tokens"]["mode"] if self.rows else SYNTHETIC
        total = sum(r["tokens"]["estimated"] for r in self.rows)
        return {
            "trajectory_version": "0.1",
            "task_id": self.task_id,
            "policy": self.policy,
            "availability_banner": self.availability_banner,
            "sandbox_root": self.sandbox_root,
            "iterations": list(self.rows),
            "final_outcome": final_outcome,
            "iterations_used": len(self.rows),
            "total_tokens": {"estimated": total, "mode": mode},
        }


__all__ = [
    "MEASURED",
    "PHASES",
    "SYNTHETIC",
    "TERMINAL_OUTCOMES",
    "Trajectory",
    "build_row",
    "surrogate_time_ms",
    "surrogate_tokens",
]
