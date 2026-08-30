"""C-05 the Verifier specification + verdict, and the loop-closing run (SPEC §4).

`VerifySpec` says *which* verification closes the loop -- tests, type-check,
lint, build, or a repo-specific check (§7.1-5). `run_verify` executes it inside
the sandbox via a bounded subprocess (K-04) and returns a `Verdict`.

VERIFIED / FAILED / ERROR are distinct (C-05 / E-03):
    VERIFIED  -- the runner ran and returned `success_exit`; the loop may settle.
    FAILED    -- the runner ran and returned a *different* exit code; the loop
                 keeps iterating (the failure is an observation, not a crash).
    ERROR     -- the runner could NOT run at all (missing binary / crash /
                 timeout); this is a distinct fault that feeds the next observe
                 and, after K-08 consecutive ERRORs, terminates the run.

The verifier runs after every modification (I-007); its captured, length-capped
`output` is the next `observe` step's input (R-07 / R-06 / §13).
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass, field

# K-02: run/experiment exit mirrors this partition.
STATUS_VERIFIED = "VERIFIED"
STATUS_FAILED = "FAILED"
STATUS_ERROR = "ERROR"

_KINDS = ("tests", "typecheck", "lint", "build", "repo_specific")


@dataclass(frozen=True)
class VerifySpec:
    """C-05: which verification closes the loop, and what exit means success."""

    kind: str
    command: str
    success_exit: int = 0

    def __post_init__(self) -> None:
        if self.kind not in _KINDS:
            raise ValueError(f"unknown VerifySpec.kind: {self.kind!r}")
        if not shlex.split(self.command):
            raise ValueError("VerifySpec.command must not be empty")


@dataclass(frozen=True)
class Verdict:
    """C-05: the structured verdict that closes the loop (R-06 / I-007)."""

    status: str      # STATUS_VERIFIED | STATUS_FAILED | STATUS_ERROR
    checks: list[dict] = field(default_factory=list)
    output: str = ""

    @property
    def passed(self) -> bool:
        return self.status == STATUS_VERIFIED


def run_verify(spec: VerifySpec, *, cwd: str, timeout_s: float = 120.0, max_output: int = 8000) -> Verdict:
    """Run `spec` inside `cwd` (the sandbox root) and return a `Verdict`.

    K-04 bounds: a hard `timeout_s` and a length-captured `output` tail so a hung
    or noisy target repo cannot wedge the run. The command is executed via the
    system shell (shlex), so a missing binary surfaces as a runner fault -> ERROR.
    """
    argv = shlex.split(spec.command)
    try:
        # check=False: a non-zero exit is a FAILED verdict we capture, not an
        # exception that would abort the loop (C-05 / E-03).
        proc = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except FileNotFoundError as exc:
        # E-03: the runner itself could not start (missing binary / shell).
        return Verdict(
            status=STATUS_ERROR,
            checks=[{"kind": spec.kind, "command": spec.command, "exit": None,
                    "output_tail": f"runner not found: {exc}"}],
            output=f"runner not found: {exc}",
    )
    except subprocess.TimeoutExpired:
        # K-04: a hung runner is an ERROR, never a false VERIFIED.
        return Verdict(
            status=STATUS_ERROR,
            checks=[{"kind": spec.kind, "command": spec.command, "exit": None,
                    "output_tail": f"timeout after {timeout_s}s"}],
            output=f"timeout after {timeout_s}s",
    )

    raw = f"{proc.stdout}\n{proc.stderr}".rstrip()
    tail = raw[-max_output:] if len(raw) > max_output else raw
    status = STATUS_VERIFIED if proc.returncode == spec.success_exit else STATUS_FAILED
    return Verdict(
        status=status,
        checks=[{"kind": spec.kind, "command": spec.command,
                "exit": proc.returncode, "output_tail": tail}],
        output=tail,
    )


__all__ = [
    "STATUS_ERROR",
    "STATUS_FAILED",
    "STATUS_VERIFIED",
    "Verdict",
    "VerifySpec",
    "run_verify",
]
