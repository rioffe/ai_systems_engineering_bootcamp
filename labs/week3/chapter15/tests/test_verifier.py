"""T-01/T-04/T-07 support (SPEC section 9): the verifier closes the loop.

`run_verify` is the agent's acceptance signal (C-05 / R-06): it runs the
repository's verification inside the sandbox and returns a structured `Verdict`
(VERIFIED / FAILED / ERROR). VERIFIED and FAILED are *distinct*: a non-zero exit
is a FAILED verdict (the loop keeps iterating), whereas a fault that stops the
runner itself -- a missing binary, a crash, a timeout -- is an ERROR (E-03) that
feeds the next observation and, after K-08 consecutive ERRORs, terminates the run.

The verifier runs after EVERY modification (I-007): its captured `output` is what
the next `observe` step reads. Output tails are length-capped (K-04) so a noisy
target repo cannot wedge the run.
"""

import sys

from coding_agent.verifier import VerifySpec, run_verify

PY = sys.executable


# ---------------------------------------------------------------- C-05 / R-06
def test_verify_spec_defaults_success_exit_zero():
    spec = VerifySpec(kind="tests", command="pytest -q")
    assert spec.success_exit == 0
    assert spec.kind == "tests"
    assert spec.command == "pytest -q"


def test_run_verify_passes_on_success_exit(tmp_path):
    spec = VerifySpec(kind="tests", command=f"{PY} -c 'import sys; sys.exit(0)'")
    verdict = run_verify(spec, cwd=str(tmp_path))
    assert verdict.status == "VERIFIED"
    assert verdict.checks[0]["kind"] == "tests"
    assert verdict.checks[0]["exit"] == 0


def test_run_verify_fails_on_nonzero_exit(tmp_path):
    spec = VerifySpec(kind="tests", command=f"{PY} -c 'import sys; sys.exit(1)'")
    verdict = run_verify(spec, cwd=str(tmp_path))
    assert verdict.status == "FAILED"    # non-zero, not a runner fault
    assert verdict.checks[0]["exit"] == 1


def test_run_verify_honors_custom_success_exit(tmp_path):
    # A build that returns 2 as its "ok" code still VERIFIES when success_exit=2.
    spec = VerifySpec(kind="build", command=f"{PY} -c 'import sys; sys.exit(2)'", success_exit=2)
    verdict = run_verify(spec, cwd=str(tmp_path))
    assert verdict.status == "VERIFIED"


# ---------------------------------------------------------------- E-03 / K-04
def test_run_verify_runner_missing_is_error_not_failed(tmp_path):
    # A missing binary is a runner fault -> ERROR (distinct from FAILED).
    spec = VerifySpec(kind="tests", command="definitely-not-a-real-binary-xyz-123")
    verdict = run_verify(spec, cwd=str(tmp_path))
    assert verdict.status == "ERROR"


def test_run_verify_output_tail_is_length_capped(tmp_path):
    # K-04: output is length-capped so a noisy runner cannot wedge the run.
    spec = VerifySpec(
        kind="lint",
        command=f"{PY} -c 'print(\"x\" * 100000)'",
        success_exit=0,
    )
    verdict = run_verify(spec, cwd=str(tmp_path), max_output=1000)
    assert len(verdict.output) <= 1000
    assert verdict.status == "VERIFIED"    # still ran; only the tail is capped


def test_run_verify_error_when_timeout_holds():
    # A hung runner times out -> ERROR (K-04), never a false VERIFIED.

    spec = VerifySpec(kind="tests", command=f"{PY} -c 'import time; time.sleep(30)'")
    verdict = run_verify(spec, cwd="/tmp", timeout_s=0.2, max_output=200)
    assert verdict.status == "ERROR"
    # no assertion on the tail length for an ERROR path
