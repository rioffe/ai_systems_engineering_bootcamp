"""R-16 / R-17 / I-012 / F-006: the single artifact writer + schema-gated loader.

`report.py` is IN the I-009 LLM/network-free core list. It is the ONLY module that
serializes durable artifacts (R-16); it writes canonical, byte-deterministic JSON
(I-002), and it loads every artifact through the "0.1" schema gate (R-17/I-012):
a malformed artifact is a deterministic LoadError (E-05), a version mismatch is a
VersionMismatch unless `--force` (E-06). It renders the offline inspect summary
(T-08) and the F-006 regression-compare delta.
"""
import json

from coding_agent.report import (
    LoadError,
    VersionMismatch,
    canonical_json,
    compare,
    load_experiment,
    load_json,
    load_trajectory,
    render_summary,
    write_json,
)


def _load_schema(name):
    with open(name, encoding="utf-8") as fh:
        return json.load(fh)


TRAJ = _load_schema("schemas/trajectory.json")
EXPER = _load_schema("schemas/experiment.json")


def _traj(final_outcome="VERIFIED", iterations=1):
    return {
            "trajectory_version": "0.1",
            "task_id": "parse-config",
            "policy": "mock",
            "availability_banner": None,
            "sandbox_root": "/sbx",
            "iterations": [
                {"iteration": 1, "tool_calls": [], "tokens": {"estimated": 10, "mode": "synthetic"},
                 "files_read": [], "files_modified": [], "tests_executed": 1,
                 "test_results": {"passed": 1, "failed": 0}, "errors": [], "time_ms": 15,
                 "verdict": "VERIFIED", "phase": "verify"}
            ],
            "final_outcome": final_outcome,
            "iterations_used": iterations,
            "total_tokens": {"estimated": 10, "mode": "synthetic"},
         }


# ---------------------------------------------------------------- R-16 / I-002 serialization
def test_canonical_json_is_byte_deterministic():
       # I-002: one writer, canonical form -> byte-identical for identical docs.
    doc = {"b": 2, "a": [1, {"y": 2, "x": 1}]}
    assert canonical_json(doc) == canonical_json({"a": [1, {"x": 1, "y": 2}], "b": 2})


def test_write_and_read_roundtrip(tmp_path):
    doc = _traj()
    path = tmp_path / "trajectory.json"
    write_json(path, doc)
    assert load_json(path) == doc
       # the on-disk text is the canonical form (re-serializing is stable).
    assert path.read_text(encoding="utf-8") == canonical_json(doc)


def test_canonical_json_ends_with_newline():
    assert canonical_json({"a": 1}).endswith("\n")


# ---------------------------------------------------------------- R-17 / I-012 / E-05 load gate
def test_load_malformed_json_is_load_error(tmp_path):
       # E-05: a malformed artifact is a deterministic load error, not a partial read.
    p = tmp_path / "bad.json"
    p.write_text("{ not json", encoding="utf-8")
    try:
        load_json(p)
        assert False, "expected LoadError"
    except LoadError:
        pass


def test_load_non_dict_is_load_error(tmp_path):
    p = tmp_path / "arr.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    try:
        load_json(p)
        assert False, "expected LoadError"
    except LoadError:
        pass


def test_load_missing_file_is_load_error(tmp_path):
    try:
        load_json(tmp_path / "nope.json")
        assert False, "expected LoadError"
    except LoadError:
        pass


def test_load_trajectory_validates_schema(tmp_path):
    p = tmp_path / "t.json"
    write_json(p, _traj())
    doc = load_trajectory(p)
    assert doc["final_outcome"] == "VERIFIED"


def test_load_rejects_missing_required_field(tmp_path):
       # T-07 / I-012: a trajectory missing any required field is a LoadError.
    doc = _traj()
    del doc["final_outcome"]
    p = tmp_path / "incomplete.json"
    write_json(p, doc)
    try:
        load_trajectory(p)
        assert False, "expected LoadError for a missing required field"
    except LoadError:
        pass


def test_load_rejects_bad_phase_value(tmp_path):
       # I-012: an out-of-vocabulary `phase` is a schema violation -> LoadError.
    doc = _traj()
    doc["iterations"][0]["phase"] = "banana"
    p = tmp_path / "badphase.json"
    write_json(p, doc)
    try:
        load_trajectory(p)
        assert False, "expected LoadError for a bad phase value"
    except LoadError:
        pass


# ---------------------------------------------------------------- E-06 version gate
def test_version_mismatch_refused(tmp_path):
    doc = _traj()
    doc["trajectory_version"] = "9.9"          # a hand-bumped version
    p = tmp_path / "bumped.json"
    write_json(p, doc)
    try:
        load_trajectory(p)
        assert False, "expected VersionMismatch"
    except VersionMismatch:
        pass


def test_version_mismatch_bypassed_by_force(tmp_path):
    doc = _traj()
    doc["trajectory_version"] = "9.9"
    p = tmp_path / "bumped.json"
    write_json(p, doc)
    loaded = load_trajectory(p, force=True)
    assert loaded["trajectory_version"] == "9.9"


def test_load_experiment_version_gate(tmp_path):
    exp = {"experiment_version": "0.1", "task_id": "parse-config",
           "injection": {"file": "src/config.py", "symbol": "parse_config",
                          "injected_defect": "wrong split delimiter",
                          "pre_injection_verdict": "FAILED"},
           "phases": [{"phase": "detect", "iteration": 1, "evidence": "test_parse_basic FAILS"}],
           "final_outcome": "VERIFIED", "iterations_to_verified": 3,
           "trajectory_ref": "trajectory.json"}
    p = tmp_path / "e.json"
    write_json(p, exp)
    assert load_experiment(p)["iterations_to_verified"] == 3
    exp["experiment_version"] = "9.9"
    write_json(p, exp)
    try:
        load_experiment(p)
        assert False, "expected VersionMismatch"
    except VersionMismatch:
        pass


# ---------------------------------------------------------------- T-08 inspect summary
def test_render_summary_is_offline_human_readable():
    s = render_summary(_traj())
    assert isinstance(s, str)
    assert "VERIFIED" in s
    assert "parse-config" in s
    assert "1" in s                       # iterations_used


def test_render_summary_reports_nonverified():
    s = render_summary(_traj(final_outcome="BUDGET_EXHAUSTED", iterations=5))
    assert "BUDGET_EXHAUSTED" in s


# ---------------------------------------------------------------- F-006 compare
def test_compare_reports_regression_delta():
    base = _traj(final_outcome="VERIFIED", iterations=1)
    cur = _traj(final_outcome="VERIFIED", iterations=4)
    rep = compare(base, cur)
    assert rep["baseline"]["iterations_used"] == 1
    assert rep["current"]["iterations_used"] == 4
    assert rep["delta"]["iterations_used"] == 3
    assert rep["regression"] is True


def test_compare_no_regression_when_equal_or_better():
    base = _traj(final_outcome="VERIFIED", iterations=4)
    cur = _traj(final_outcome="VERIFIED", iterations=2)
    assert compare(base, cur)["regression"] is False


def test_compare_worse_outcome_is_regression():
    base = _traj(final_outcome="VERIFIED", iterations=1)
    cur = _traj(final_outcome="ERROR", iterations=3)
    rep = compare(base, cur)
    assert rep["regression"] is True
    assert rep["delta"]["final_outcome"] == "ERROR"
