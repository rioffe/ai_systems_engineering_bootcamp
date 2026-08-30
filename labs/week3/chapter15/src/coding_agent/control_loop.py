# R-01 / R-08 / C-08 / I-001 / I-006 / K-08: the deterministic closed-loop state machine.
#
# `control_loop.py` is IN the I-009 LLM/network-free core list. It drives ONE run
# through the section-3.2 FSM -- OBSERVE -> REASON -> PERMIT -> ACT -> VERIFY ->
# FEEDBACK -- closing the loop on the CANONICAL verifier's verdict (R-06/I-007)
# and settling in exactly ONE of the C-08 terminals:
#
#     VERIFIED(0) | BUDGET_EXHAUSTED(1) | STALLED:NOOP(1) | STALLED:BUDGET(1)
#     | DENIED_LOOP(1) | ERROR(5)
#
# Invariants honored here:
#   * I-001  -- bounded: a run runs at most `max_iterations` iterations.
#   * I-006  -- a policy-declared STOP is success ONLY if the verifier is VERIFIED.
#   * I-008  -- a DENY is recorded (errors + tool_calls) and has NO side-effect;
#               a single DENY routes to the next REASON, a K-08 consecutive-DENY
#               cycle reaches DENIED_LOOP.
#   * E-02   -- an unrecognizable policy action is coerced to an explicit ERROR
#               (recorded in `errors`), never a silent no-op.
#   * E-03   -- K-08 consecutive verifier ERROR verdicts terminate ERROR (exit 5).
#   * E-13   -- a --no-compact context overflow reaches STALLED:BUDGET (exit 1).
#   * K-08   -- consecutive ERROR / NOOP / DENY budgets drive the non-VERIFIED
#               terminals; a single error/deny never terminates.
#
# The loop is a pure function of its inputs on the mock path, so it is
# byte-deterministic (I-002). Unit tests inject a canned `verify` callable so no
# subprocess runs at the unit level; the integration test uses the real runner.

from __future__ import annotations

import os
from dataclasses import dataclass

from .context import BudgetOverflow
from .instrument import Trajectory, build_row
from .permissions import authorize
from .policy import NOOP, STOP, ToolCall, UnrecognizedAction, coerce_action
from .tools import EditResult
from .verifier import (
    STATUS_ERROR,
    STATUS_FAILED,
    STATUS_VERIFIED,
    Verdict,
    run_verify,
)

# C-08 terminal -> exit code (F-003 partition).
_OUTCOME_EXIT = {
    "VERIFIED": 0,
    "BUDGET_EXHAUSTED": 1,
    "STALLED:NOOP": 1,
    "STALLED:BUDGET": 1,
    "DENIED_LOOP": 1,
    "ERROR": 5,
}


# The outcome of one run: the terminal label, its exit code, the finalized C-06
# trajectory document, the iterations actually run, and the last verifier verdict.
@dataclass(frozen=True)
class RunResult:
    final_outcome: str
    exit_code: int
    iterations_used: int
    trajectory: dict
    verdict: Verdict | None = None


def _default_verify(task, sandbox_root) -> Verdict:
    # The canonical verifier: run the task's VerifySpec inside the sandbox (R-06).
    return run_verify(task.verifier, cwd=sandbox_root)


def _observe(sandbox_root: str) -> dict:
    # OBSERVE: a deterministic snapshot of the sandbox repo state (O_t).
    files = []
    for dirpath, _dirs, fs in os.walk(sandbox_root):
        for name in sorted(fs):
            if not name.startswith("."):
                files.append(os.path.relpath(os.path.join(dirpath, name), sandbox_root))
    return {"files": files}


def _tally(verdict: Verdict) -> dict | None:
    # C-06 test_results: pass/fail tallies, null when no check ran. The runner
    # emits one check per invocation; the status is verdict-level.
    n = len(verdict.checks)
    if n == 0:
        return None
    if verdict.status == STATUS_VERIFIED:
        return {"passed": n, "failed": 0}
    return {"passed": 0, "failed": n}


def _phase(batch: list, prev_status: str | None) -> str:
    # F-008: the instrumentation label for this iteration's dominant FSM move.
    if any(isinstance(a, STOP) for a in batch):
        return "stop"
    names = [a.name for a in batch if isinstance(a, ToolCall)]
    if "edit_file" in names:
        return "repair" if prev_status == STATUS_FAILED else "modify"
    if "search" in names:
        return "search"
    if "read_file" in names or "list_files" in names:
        return "inspect"
    return "observe"


def _act(
    call: ToolCall,
    controller,  # nosemgrep -- opengrep `auto` misfires: sandboxed ToolController,
    # a permission-gated executor (C-03/C-04); there is no SQL in this harness.
    context,
    files_read: list,
    files_modified: list,
    errors: list,
) -> tuple:
    # ACT: execute one APPROVED tool call in the sandbox (R-04), folding its
    # result into the context working set and the F-013 counters. Returns
    # (executed, faulted): executed = a real tool side-effect ran; faulted = the
    # call raised (recorded as an iteration error, E-02-class, counted by K-08).
    try:
        result = controller.execute(call)
    except Exception as exc:  # noqa: BLE001 -- deliberate fault boundary: ANY tool
        # fault (KeyError, PathEscape, OSError, ...) is a recorded iteration error,
        # never an uncaught exception that would kill the run (E-02/E-03 semantics).
        errors.append(f"tool {call.name} error: {exc}")
        return (False, True)
    if call.name == "read_file":
        path = call.args["path"]
        context.add_file(path, result)  # I-005: selected, not bulk
        files_read.append(path)
        return (True, False)
    if call.name == "edit_file":
        if isinstance(result, EditResult) and result.applied:
            files_modified.append(call.args["path"])
            # R-10 salient state: refresh the open edit's latest content.
            try:
                with open(os.path.join(controller.root, call.args["path"]), encoding="utf-8") as fh:
                    context.add_file(call.args["path"], fh.read())
            except OSError:
                pass
            return (True, False)
        return (False, False)  # E-14: a failed edit is not a modification
    if call.name == "run_shell":
        context.add_feedback(f"$ {call.args.get('command', '')}\n{result.out}{result.err}")
        return (True, False)
    # list_files / search: discovery only (F-013: no files_read increment).
    return (True, False)


def run(
    *,
    task,
    policy,
    pconfig,
    controller,
    sandbox_root: str,
    context,
    max_iterations: int = 8,
    max_consecutive_errors: int = 2,
    max_consecutive_noops: int | None = None,
    availability_banner: str | None = None,
    policy_name: str = "mock",
    verify=None,
) -> RunResult:
    # Drive one bounded closed-loop run (R-01) to exactly one C-08 terminal.
    if max_iterations < 1:
        raise ValueError(f"max_iterations must be a positive integer (K-03), got {max_iterations}")
    if max_consecutive_noops is None:
        max_consecutive_noops = max(1, max_iterations // 2)
    if verify is None:
        verify = _default_verify

    traj = Trajectory(
        task_id=task.task_id,
        policy=policy_name,
        sandbox_root=sandbox_root,
        availability_banner=availability_banner,
    )
    consec_errors = 0
    consec_noops = 0
    consec_denies = 0
    prev_status: str | None = None
    last_verdict: Verdict | None = None
    outcome: str | None = None
    iterations_used = 0

    for t in range(1, max_iterations + 1):
        iterations_used = t

        # OBSERVE -- snapshot the sandbox repo state (O_t).
        observation = _observe(sandbox_root)

        # REASON -- compose C_t (K-05/K-09 budget) and let the policy pick A_t.
        try:
            ctx = context.compose(task, t)
        except BudgetOverflow:
            outcome = "STALLED:BUDGET"  # E-13: --no-compact overflow
            break
        batch_raw = policy.select(ctx, observation)

        # Coerce the batch against the closed action space (E-02 / I-004).
        batch: list = []
        errors: list[str] = []
        n_action_errors = 0
        for a in batch_raw:
            try:
                batch.append(coerce_action(a))
            except UnrecognizedAction as exc:
                errors.append(f"E-02 unrecognizable action: {exc.value!r}")
                n_action_errors += 1

        # PERMIT + ACT -- gate every tool call, execute the approved ones.
        tool_calls: list[dict] = []
        files_read: list[str] = []
        files_modified: list[str] = []
        n_toolcalls = 0
        n_denied = 0
        n_tool_faults = 0
        for a in batch:
            if isinstance(a, STOP):
                tool_calls.append({"name": "STOP", "args": {}})
            elif isinstance(a, NOOP):
                tool_calls.append({"name": "NOOP", "args": {}})
            else:
                n_toolcalls += 1
                tool_calls.append({"name": a.name, "args": dict(a.args)})
                decision = authorize(a, pconfig, sandbox_root)
                if not decision.allows:
                    n_denied += 1
                    errors.append(f"DENY {a.name}: {decision.reason}")
                else:
                    _executed, _faulted = _act(
                        a, controller, context, files_read, files_modified, errors
                    )
                    if _faulted:
                        n_tool_faults += 1

        # VERIFY -- the canonical verifier closes the loop (R-06 / I-007).
        verdict = verify(task, sandbox_root)
        last_verdict = verdict
        if verdict.status == STATUS_ERROR:
            tests_executed = 0
            test_results = None
        else:
            tests_executed = len(verdict.checks)
            test_results = _tally(verdict)
        row = build_row(
            iteration=t,
            tool_calls=tool_calls,
            context_chars=ctx.chars,
            files_read=files_read,
            files_modified=files_modified,
            tests_executed=tests_executed,
            test_results=test_results,
            errors=errors,
            verdict=verdict.status,
            phase=_phase(batch, prev_status),
        )
        traj.add_row(row)

        # K-08 consecutive-failure budgets. A DENY records an error but does NOT
        # count as an ERROR iteration (C-08: a single DENY routes to next REASON).
        if verdict.status == STATUS_ERROR or n_action_errors or n_tool_faults:
            consec_errors += 1
        else:
            consec_errors = 0
        if n_toolcalls and n_denied == n_toolcalls:
            consec_denies += 1
            consec_noops = 0
        elif n_toolcalls:
            consec_denies = 0
            consec_noops = 0
        else:
            consec_noops += 1
            consec_denies = 0

        # FEEDBACK -- a VERIFIED verdict is the ONLY path to VERIFIED (I-006).
        if verdict.status == STATUS_VERIFIED:
            outcome = "VERIFIED"
            break
        context.add_feedback(f"verdict={verdict.status}\n{verdict.output}")
        prev_status = verdict.status

        if consec_errors >= max_consecutive_errors:
            outcome = "ERROR"
            break
        if consec_denies >= max_consecutive_noops:
            outcome = "DENIED_LOOP"
            break
        if consec_noops >= max_consecutive_noops:
            outcome = "STALLED:NOOP"
            break
    else:
        # I-001: the bounded cap was reached without a terminal -> BUDGET_EXHAUSTED.
        outcome = "BUDGET_EXHAUSTED"

    doc = traj.finalize(outcome)
    return RunResult(
        final_outcome=outcome,
        exit_code=_OUTCOME_EXIT[outcome],
        iterations_used=iterations_used,
        trajectory=doc,
        verdict=last_verdict,
    )


__all__ = [
    "RunResult",
    "run",
]
