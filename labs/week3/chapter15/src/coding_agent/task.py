"""C-01 the Task input (SPEC section 4 / C-01, R-01).

A `Task` is the input to one closed-loop run: a natural-language `prompt`, the
`target_repo` to copy into the sandbox, and the `VerifySpec` that closes the loop
(C-05 / R-06). `success_token` / `acceptance_test` are MAY sub-criteria (C-01)
used by the optional `--baseline` System-A/B demo (R-18).
"""

from __future__ import annotations

from dataclasses import dataclass

from .verifier import VerifySpec


@dataclass(frozen=True)
class Task:
    """C-01: the input to one closed-loop run.

    `verifier` (the C-05 spec that runs the loop's acceptance check) is required;
    everything else is part of the minimal section-17 pipeline input.
    """

    task_id: str
    prompt: str
    target_repo: str
    verifier: VerifySpec
    success_token: str | None = None
    acceptance_test: str | None = None

    def __post_init__(self) -> None:
        if not self.task_id:
            raise ValueError("Task.task_id must be non-empty")
        if not self.prompt:
            raise ValueError("Task.prompt must be non-empty")
        if not self.target_repo:
            raise ValueError("Task.target_repo must be non-empty")


__all__ = ["Task"]
