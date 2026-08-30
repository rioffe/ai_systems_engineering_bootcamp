"""R-11 / C-07 / C-09 / I-013 / T-04 / T-11: the section-17 failure-injection experiment.

`experiment.py` orchestrates the pinned `parse-config` arc: copy the C-09 fixture
into a sandbox, inject the canonical defect, run the deterministic loop over a
scripted detect -> diagnose -> repair `MockPolicy`, and emit the C-07
`experiment.json` (versioned, schema-gated) recording the three phases and the
pinned `iterations_to_verified == 3`. Unit tests inject a canned `verify` so no
subprocess runs here; the integration test (T-04/T-11) drives the real fixture +
real verifier.
"""

import json
import os

from coding_agent.context import ContextManager
from coding_agent.experiment import (
    PARSE_CONFIG_DEFECT,
    DefectSpec,
    ExperimentResult,
    InjectionError,
    inject_defect,
    repair_arc_policy,
    run_experiment,
)
from coding_agent.permissions import PermsConfig
from coding_agent.policy import MockPolicy
from coding_agent.task import Task
from coding_agent.tools import ToolController
from coding_agent.verifier import STATUS_FAILED, STATUS_VERIFIED, Verdict, VerifySpec


def _task():
    return Task(
        task_id="parse-config",
        prompt="fix the parser",
        target_repo="/repo",
        verifier=VerifySpec(kind="tests", command="pytest -q"),
    )


def _setup(tmp_path, body="if line == '' or delimiter not in line:\n"):
    root = tmp_path / "sbx"
    (root / "repo").mkdir(parents=True)
    (root / "repo" / "config.py").write_text(body, encoding="utf-8")
    r = str(root)
    return r, ToolController(r), PermsConfig(sandbox_root=r)


# ---------------------------------------------------------------- defect + injection
def test_defect_spec_is_the_pinned_c09_defect():
    # C-09 / I-013: the canonical defect is pinned, so the arc is reproducible.
    d = PARSE_CONFIG_DEFECT
    assert d.file == "repo/config.py"
    assert d.symbol == "parse_config"
    assert d.old == "delimiter not in line"
    assert d.new == "delimiter in line"
    assert d.pre_injection_verdict == "FAILED"


def test_inject_defect_breaks_the_code(tmp_path):
    r, controller, _ = _setup(tmp_path)
    inject_defect(controller, PARSE_CONFIG_DEFECT)
    with open(os.path.join(r, "repo", "config.py"), encoding="utf-8") as fh:
        text = fh.read()
    assert "delimiter in line" in text
    assert "delimiter not in line" not in text


def test_inject_defect_fails_if_token_absent(tmp_path):
    # a defect whose `old` token is missing is a deterministic error, not a silent no-op
    _, controller, _ = _setup(tmp_path, body="nothing to inject here\n")
    d = DefectSpec(
        file="repo/config.py", symbol="x", injected_defect="x", old="not-present", new="new"
    )
    try:
        inject_defect(controller, d)
        assert False, "expected an injection failure"
    except InjectionError as exc:
        assert "inject" in str(exc).lower()


# ---------------------------------------------------------------- repair-arc policy
def test_repair_arc_policy_is_a_three_iteration_script():
    policy = repair_arc_policy(
        PARSE_CONFIG_DEFECT, probe_file="repo/config.py", probe_query="delimiter"
    )
    assert isinstance(policy, MockPolicy)
    batches = policy.select_all()
    assert len(batches) == 3
    # iter 3 is the repair edit_file that reverses the defect
    assert batches[2][0].name == "edit_file"
    assert batches[2][0].args["old"] == PARSE_CONFIG_DEFECT.new
    assert batches[2][0].args["new"] == PARSE_CONFIG_DEFECT.old


# ---------------------------------------------------------------- T-04 arc (unit, canned verify)
def test_experiment_arc_detect_diagnose_repair(tmp_path):
    r, controller, pconfig = _setup(tmp_path)
    policy = repair_arc_policy(
        PARSE_CONFIG_DEFECT, probe_file="repo/config.py", probe_query="delimiter"
    )
    calls = {"n": 0}

    def v(task, sandbox_root):
        calls["n"] += 1
        status = STATUS_VERIFIED if calls["n"] >= 3 else STATUS_FAILED
        return Verdict(
            status=status,
            checks=[{"n": 1}],
            output="test_parse_basic FAILS" if status == STATUS_FAILED else "ok",
        )

    res = run_experiment(
        task=_task(),
        defect=PARSE_CONFIG_DEFECT,
        policy=policy,
        pconfig=pconfig,
        controller=controller,
        sandbox_root=r,
        context=ContextManager(budget=10000),
        verify=v,
        max_iterations=8,
    )
    assert isinstance(res, ExperimentResult)
    assert res.final_outcome == "VERIFIED"
    assert res.exit_code == 0
    assert res.iterations_to_verified == 3
    phases = {p["phase"]: p["iteration"] for p in res.experiment["phases"]}
    assert phases == {"detect": 1, "diagnose": 2, "repair": 3}


# ---------------------------------------------------------------- C-07 doc
def test_experiment_doc_is_c07_and_validates(tmp_path):
    r, controller, pconfig = _setup(tmp_path)
    policy = repair_arc_policy(
        PARSE_CONFIG_DEFECT, probe_file="repo/config.py", probe_query="delimiter"
    )
    calls = {"n": 0}

    def v(task, sandbox_root):
        calls["n"] += 1
        return Verdict(
            status=STATUS_VERIFIED if calls["n"] >= 3 else STATUS_FAILED, checks=[{"n": 1}]
        )

    res = run_experiment(
        task=_task(),
        defect=PARSE_CONFIG_DEFECT,
        policy=policy,
        pconfig=pconfig,
        controller=controller,
        sandbox_root=r,
        context=ContextManager(budget=10000),
        verify=v,
        max_iterations=8,
    )
    doc = res.experiment
    assert doc["experiment_version"] == "0.1"
    assert doc["task_id"] == "parse-config"
    assert doc["injection"]["file"] == "repo/config.py"
    assert doc["injection"]["symbol"] == "parse_config"
    assert doc["injection"]["pre_injection_verdict"] == "FAILED"
    assert doc["final_outcome"] == "VERIFIED"
    assert doc["iterations_to_verified"] == 3
    assert doc["trajectory_ref"] == "trajectory.json"
    # validate against the C-07 schema
    with open("schemas/experiment.json", encoding="utf-8") as fh:
        schema = json.load(fh)
    import jsonschema

    jsonschema.validate(doc, schema)


# ---------------------------------------------------------------- T-11 byte-identity
def test_experiment_doc_is_byte_identical_across_runs(tmp_path):
    def build(t):
        r, controller, pconfig = _setup(t)
        policy = repair_arc_policy(
            PARSE_CONFIG_DEFECT, probe_file="repo/config.py", probe_query="delimiter"
        )
        calls = {"n": 0}

        def v(task, sandbox_root):
            calls["n"] += 1
            return Verdict(
                status=STATUS_VERIFIED if calls["n"] >= 3 else STATUS_FAILED, checks=[{"n": 1}]
            )

        res = run_experiment(
            task=_task(),
            defect=PARSE_CONFIG_DEFECT,
            policy=policy,
            pconfig=pconfig,
            controller=controller,
            sandbox_root=r,
            context=ContextManager(budget=10000),
            verify=v,
            max_iterations=8,
        )
        return json.dumps(res.experiment, indent=2, sort_keys=True)

    a, b = build(tmp_path / "a"), build(tmp_path / "b")
    assert a == b  # I-013: byte-identical, pinned iterations_to_verified


# ---------------------------------------------------------------- non-verified experiment
def test_experiment_not_verified_reports_failure(tmp_path):
    # a policy that never repairs -> not VERIFIED, exit 1, iterations_to_verified 0
    r, controller, pconfig = _setup(tmp_path)
    from coding_agent.policy import NOOP

    policy = MockPolicy(script=[[NOOP()]] * 8)
    res = run_experiment(
        task=_task(),
        defect=PARSE_CONFIG_DEFECT,
        policy=policy,
        pconfig=pconfig,
        controller=controller,
        sandbox_root=r,
        context=ContextManager(budget=10000),
        verify=lambda task, sr: Verdict(status=STATUS_FAILED, checks=[{"n": 1}]),
        max_iterations=8,
    )
    assert res.final_outcome != "VERIFIED"
    assert res.exit_code in (1, 5)
    assert res.iterations_to_verified == 0
    assert res.experiment["final_outcome"] != "VERIFIED"
