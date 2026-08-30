"""R-01 / R-08 / C-08 / I-001 / I-006: the deterministic closed-loop state machine.

`control_loop.py` is IN the I-009 LLM/network-free core list. It drives one run
through OBSERVE -> REASON -> PERMIT -> ACT -> VERIFY -> FEEDBACK, closing the loop
on the canonical verifier's verdict (R-06/I-007) and settling in exactly one of
the C-08 terminals:

    VERIFIED(0) | BUDGET_EXHAUSTED(1) | STALLED:NOOP(1) | STALLED:BUDGET(1)
    | DENIED_LOOP(1) | ERROR(5)

A policy-declared STOP is accepted as VERIFIED only if the verifier is also
VERIFIED (I-006). The loop is bounded (I-001) and byte-deterministic on the mock
path (I-002). Unit tests inject a canned `verify` so no subprocess runs here.
"""

import os

from coding_agent.context import ContextManager
from coding_agent.control_loop import RunResult, run
from coding_agent.permissions import PermsConfig
from coding_agent.policy import NOOP, STOP, ToolCall
from coding_agent.task import Task
from coding_agent.tools import ToolController
from coding_agent.verifier import STATUS_ERROR, STATUS_FAILED, STATUS_VERIFIED, Verdict, VerifySpec


def _task():
    return Task(
        task_id="parse-config",
        prompt="fix the parser",
        target_repo="/repo",
        verifier=VerifySpec(kind="tests", command="pytest -q"),
    )


def _setup(tmp_path):
    root = tmp_path / "sbx"
    (root / "repo").mkdir(parents=True)
    (root / "repo" / "config.py").write_text("X = 1\n", encoding="utf-8")
    r = str(root)
    return r, ToolController(r), PermsConfig(sandbox_root=r)


def _verify(status, checks=(), output=""):
    def _v(task, sandbox_root):
        return Verdict(status=status, checks=list(checks), output=output)

    return _v


# A policy that replays the SAME batch every iteration (never progresses on its own).
class _Always:
    def __init__(self, batch):
        self.batch = list(batch)

    def select(self, context, observation):
        return list(self.batch)


def _verdict(status, checks=(), output=""):
    return Verdict(status=status, checks=list(checks), output=output)


# ---------------------------------------------------------------- R-01 / T-01 VERIFIED
def test_verified_in_one_iteration(tmp_path):
    r, controller, pconfig = _setup(tmp_path)
    res = run(
        task=_task(),
        policy=_Always([STOP()]),
        pconfig=pconfig,
        controller=controller,
        sandbox_root=r,
        context=ContextManager(budget=10000),
        max_iterations=8,
        verify=_verify(STATUS_VERIFIED, checks=[{"n": 1}]),
    )
    assert res.final_outcome == "VERIFIED"
    assert res.exit_code == 0
    assert res.trajectory["iterations_used"] == 1
    assert res.trajectory["final_outcome"] == "VERIFIED"


def test_verified_requires_verifier(tmp_path):
    # I-006: a policy STOP is NOT success unless the verifier is also VERIFIED.
    r, controller, pconfig = _setup(tmp_path)
    res = run(
        task=_task(),
        policy=_Always([STOP()]),
        pconfig=pconfig,
        controller=controller,
        sandbox_root=r,
        context=ContextManager(budget=10000),
        max_iterations=3,
        verify=_verify(STATUS_FAILED),
    )
    assert res.final_outcome != "VERIFIED"
    assert res.exit_code != 0


# ---------------------------------------------------------------- R-08 / T-06 budget
def test_budget_exhausted_at_cap(tmp_path):
    # T-06: never-VERIFIED run with --max-iterations 5 stops at the 5th row, exit 1.
    r, controller, pconfig = _setup(tmp_path)
    policy = _Always([ToolCall("read_file", {"path": "repo/config.py"})])
    res = run(
        task=_task(),
        policy=policy,
        pconfig=pconfig,
        controller=controller,
        sandbox_root=r,
        context=ContextManager(budget=10000),
        max_iterations=5,
        verify=_verify(STATUS_FAILED),
    )
    assert res.final_outcome == "BUDGET_EXHAUSTED"
    assert res.exit_code == 1
    assert res.trajectory["iterations_used"] == 5
    assert [row["iteration"] for row in res.trajectory["iterations"]] == [1, 2, 3, 4, 5]


def test_noop_policy_stalls(tmp_path):
    # K-08: consecutive NOOPs (default max_iterations//2) -> STALLED:NOOP, exit 1.
    r, controller, pconfig = _setup(tmp_path)
    res = run(
        task=_task(),
        policy=_Always([NOOP()]),
        pconfig=pconfig,
        controller=controller,
        sandbox_root=r,
        context=ContextManager(budget=10000),
        max_iterations=6,
        verify=_verify(STATUS_FAILED),
    )
    assert res.final_outcome == "STALLED:NOOP"
    assert res.exit_code == 1


# ---------------------------------------------------------------- C-08 / E-13 STALLED:BUDGET
def test_no_compact_overflow_is_stalled_budget(tmp_path):
    r, controller, pconfig = _setup(tmp_path)
    # a --no-compact context that overflows on the first compose
    ctx = ContextManager(budget=10, compact=False)
    ctx.add_file("big.py", "x" * 200)
    res = run(
        task=_task(),
        policy=_Always([STOP()]),
        pconfig=pconfig,
        controller=controller,
        sandbox_root=r,
        context=ctx,
        max_iterations=8,
        verify=_verify(STATUS_VERIFIED),
    )
    assert res.final_outcome == "STALLED:BUDGET"
    assert res.exit_code == 1


# ---------------------------------------------------------------- C-08 / E-03 ERROR
def test_consecutive_verifier_errors_terminate_error(tmp_path):
    # E-03 / K-08: K-08 consecutive ERROR verdicts -> ERROR, exit 5.
    r, controller, pconfig = _setup(tmp_path)
    res = run(
        task=_task(),
        policy=_Always([STOP()]),
        pconfig=pconfig,
        controller=controller,
        sandbox_root=r,
        context=ContextManager(budget=10000),
        max_iterations=8,
        max_consecutive_errors=2,
        verify=_verify(STATUS_ERROR),
    )
    assert res.final_outcome == "ERROR"
    assert res.exit_code == 5


def test_single_error_does_not_terminate(tmp_path):
    # E-03: a single ERROR feeds the next iteration and recovers to VERIFIED.
    r, controller, pconfig = _setup(tmp_path)
    calls = {"n": 0}

    def v(task, sandbox_root):
        calls["n"] += 1
        return Verdict(status=STATUS_ERROR if calls["n"] == 1 else STATUS_VERIFIED)

    res = run(
        task=_task(),
        policy=_Always([STOP()]),
        pconfig=pconfig,
        controller=controller,
        sandbox_root=r,
        context=ContextManager(budget=10000),
        max_iterations=8,
        max_consecutive_errors=2,
        verify=v,
    )
    assert res.final_outcome == "VERIFIED"
    assert calls["n"] == 2


# ---------------------------------------------------------------- C-08 / I-008 DENIED_LOOP
def test_repeated_denied_cycle_reaches_denied_loop(tmp_path):
    # K-08: a repeated all-DENY cycle reaches DENIED_LOOP (exit 1).
    r, controller, pconfig = _setup(tmp_path)
    # edit_file outside the sandbox root -> DENY every iteration
    policy = _Always(
        [ToolCall("edit_file", {"path": "../../escape.py", "op": "append", "new": "x"})]
    )
    res = run(
        task=_task(),
        policy=policy,
        pconfig=pconfig,
        controller=controller,
        sandbox_root=r,
        context=ContextManager(budget=10000),
        max_iterations=6,
        verify=_verify(STATUS_FAILED),
    )
    assert res.final_outcome == "DENIED_LOOP"
    assert res.exit_code == 1


def test_deny_does_not_terminate_alone(tmp_path):
    # C-08: a single DENY routes to the next REASON; it does not end the run.
    r, controller, pconfig = _setup(tmp_path)

    # iter 1: a denied edit; then the policy recovers to a STOP + VERIFIED.
    class _Recover:
        def __init__(self):
            self.n = 0

        def select(self, context, observation):
            self.n += 1
            if self.n == 1:
                return [
                    ToolCall("edit_file", {"path": "../../escape.py", "op": "append", "new": "x"})
                ]
            return [STOP()]

    res = run(
        task=_task(),
        policy=_Recover(),
        pconfig=pconfig,
        controller=controller,
        sandbox_root=r,
        context=ContextManager(budget=10000),
        max_iterations=6,
        verify=_verify(STATUS_VERIFIED),
    )
    assert res.final_outcome == "VERIFIED"


# ---------------------------------------------------------------- C-06 / I-010 instrumentation
def test_iteration_rows_carry_full_field_set(tmp_path):
    r, controller, pconfig = _setup(tmp_path)
    policy = _Always([ToolCall("read_file", {"path": "repo/config.py"})])
    res = run(
        task=_task(),
        policy=policy,
        pconfig=pconfig,
        controller=controller,
        sandbox_root=r,
        context=ContextManager(budget=10000),
        max_iterations=2,
        verify=_verify(STATUS_FAILED, checks=[{"n": 1}]),
    )
    for row in res.trajectory["iterations"]:
        assert set(row) == {
            "iteration",
            "tool_calls",
            "tokens",
            "files_read",
            "files_modified",
            "tests_executed",
            "test_results",
            "errors",
            "time_ms",
            "verdict",
            "phase",
        }
    row1 = res.trajectory["iterations"][0]
    assert row1["tool_calls"] == [{"name": "read_file", "args": {"path": "repo/config.py"}}]
    assert row1["files_read"] == ["repo/config.py"]
    assert row1["tests_executed"] == 1
    assert row1["verdict"] == "FAILED"


def test_files_modified_counts_applied_edits(tmp_path):
    r, controller, pconfig = _setup(tmp_path)
    policy = _Always(
        [ToolCall("edit_file", {"path": "repo/config.py", "op": "append", "new": "\nY=2"})]
    )
    res = run(
        task=_task(),
        policy=policy,
        pconfig=pconfig,
        controller=controller,
        sandbox_root=r,
        context=ContextManager(budget=10000),
        max_iterations=2,
        verify=_verify(STATUS_FAILED),
    )
    assert res.trajectory["iterations"][0]["files_modified"] == ["repo/config.py"]
    # the edit actually landed in the sandbox copy
    with open(os.path.join(r, "repo", "config.py"), encoding="utf-8") as fh:
        assert "Y=2" in fh.read()


def test_denied_call_recorded_in_errors_and_tool_calls(tmp_path):
    r, controller, pconfig = _setup(tmp_path)
    policy = _Always(
        [ToolCall("edit_file", {"path": "../../escape.py", "op": "append", "new": "x"})]
    )
    res = run(
        task=_task(),
        policy=policy,
        pconfig=pconfig,
        controller=controller,
        sandbox_root=r,
        context=ContextManager(budget=10000),
        max_iterations=2,
        verify=_verify(STATUS_FAILED),
    )
    row1 = res.trajectory["iterations"][0]
    # the denied call is recorded in tool_calls (F-013) and errors (I-008), no side-effect
    assert any("DENY" in e for e in row1["errors"])
    assert row1["files_modified"] == []


# ---------------------------------------------------------------- I-001 boundedness
def test_never_exceeds_max_iterations(tmp_path):
    r, controller, pconfig = _setup(tmp_path)
    policy = _Always([ToolCall("read_file", {"path": "repo/config.py"})])
    res = run(
        task=_task(),
        policy=policy,
        pconfig=pconfig,
        controller=controller,
        sandbox_root=r,
        context=ContextManager(budget=10000),
        max_iterations=4,
        verify=_verify(STATUS_FAILED),
    )
    assert len(res.trajectory["iterations"]) <= 4


def test_result_type_and_shape(tmp_path):
    r, controller, pconfig = _setup(tmp_path)
    res = run(
        task=_task(),
        policy=_Always([STOP()]),
        pconfig=pconfig,
        controller=controller,
        sandbox_root=r,
        context=ContextManager(budget=10000),
        max_iterations=8,
        verify=_verify(STATUS_VERIFIED),
    )
    assert isinstance(res, RunResult)
    assert res.trajectory["policy"] == "mock"
    assert res.trajectory["availability_banner"] is None
    assert res.trajectory["sandbox_root"] == r
