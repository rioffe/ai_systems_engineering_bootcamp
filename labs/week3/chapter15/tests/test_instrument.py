"""C-06 / F-013 / K-07 / I-010 / I-002: trajectory instrumentation.

Every iteration row carries exactly the C-06 field set (I-010); the mock path
uses the pinned K-07 surrogate formulas, labeled `synthetic`; files_read /
files_modified are DISTINCT (F-013) and only read_file / applied edit_file
count; the serialized document is byte-identical across runs (I-002).
"""
import json

import jsonschema

from coding_agent.instrument import (
    PHASES,
    TERMINAL_OUTCOMES,
    Trajectory,
    build_row,
    surrogate_time_ms,
    surrogate_tokens,
)

with open("schemas/trajectory.json") as _fh:
    SCHEMA = json.load(_fh)


# ---------------------------------------------------------------- K-07 surrogates
def test_k07_token_formula():
       # tokens.estimated = len(C_t chars) + 4 * len(tool_calls)
    assert surrogate_tokens(1816, 3) == 1828
    assert surrogate_tokens(0, 0) == 0


def test_k07_time_formula():
       # time_ms = 5 * iteration + len(tool_calls) * 10   (1-based iteration, F-001)
    assert surrogate_time_ms(1, 3) == 5 + 30
    assert surrogate_time_ms(4, 1) == 20 + 10


def test_token_counter_is_synthetic():
       # E-04 / R-13: mock surrogate counters are labeled synthetic.
    row = build_row(iteration=1, tool_calls=[{"name": "read_file", "args": {"path": "a.py"}}],
                    context_chars=10)
    assert row["tokens"] == {"estimated": 14, "mode": "synthetic"}
    assert row["time_ms"] == surrogate_time_ms(1, 1)


# ---------------------------------------------------------------- F-013 counting rules
def test_files_read_distinct_and_in_order():
    row = build_row(iteration=2, tool_calls=[], context_chars=0,
                    files_read=["b.py", "a.py", "b.py"])
    assert row["files_read"] == ["b.py", "a.py"]


def test_files_modified_distinct_applied_only():
    row = build_row(iteration=2, tool_calls=[], context_chars=0,
                    files_modified=["a.py", "a.py"])
    assert row["files_modified"] == ["a.py"]


def test_every_field_present_on_every_row():
       # I-010 totality: every C-06 field must be present on the row.
    row = build_row(iteration=1, tool_calls=[{"name": "list_files", "args": {"path": "."}}],
                    context_chars=50)
    expected = {"iteration", "tool_calls", "tokens", "files_read", "files_modified",
                "tests_executed", "test_results", "errors", "time_ms", "verdict", "phase"}
    assert set(row) == expected
    assert row["verdict"] == "PENDING"
    assert row["test_results"] is None
    assert row["errors"] == []


# ---------------------------------------------------------------- phase / verdict vocab
def test_phase_must_be_in_pinned_vocabulary():
       # F-008: phase is one of the pinned 8-value enum.
    assert set(PHASES) == {"observe", "inspect", "search", "propose",
                           "modify", "verify", "repair", "stop"}
    for p in PHASES:
        assert build_row(iteration=1, tool_calls=[], context_chars=0,
                         phase=p)["phase"] == p


def test_bad_phase_rejected():
    try:
        build_row(iteration=1, tool_calls=[], context_chars=0, phase="banana")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_iteration_is_1_based():
       # F-001: iterations are 1-based; 0 is rejected.
    try:
        build_row(iteration=0, tool_calls=[], context_chars=0)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_verdict_tracks_verifier():
    assert build_row(iteration=1, tool_calls=[], context_chars=0,
                     tests_executed=2, test_results={"passed": 1, "failed": 1},
                     verdict="FAILED")["verdict"] == "FAILED"


# ---------------------------------------------------------------- C-06 envelope
def test_envelope_finalize_and_totals():
    tr = Trajectory(task_id="parse-config", policy="mock", sandbox_root="/sbx")
    tr.add_row(build_row(iteration=1, tool_calls=[{"name": "run_shell", "args": {"command": "pytest -q"}}],
                     context_chars=100, tests_executed=2,
                     test_results={"passed": 1, "failed": 1}, verdict="FAILED", phase="verify"))
    tr.add_row(build_row(iteration=2, tool_calls=[{"name": "edit_file", "args": {"path": "a.py"}},
                                                   {"name": "run_shell", "args": {"command": "pytest -q"}}],
                     context_chars=200, tests_executed=2,
                     test_results={"passed": 2, "failed": 0}, verdict="VERIFIED", phase="repair"))
    doc = tr.finalize("VERIFIED")
    assert doc["trajectory_version"] == "0.1"
    assert doc["task_id"] == "parse-config"
    assert doc["availability_banner"] is None
    assert doc["final_outcome"] == "VERIFIED"
    assert doc["iterations_used"] == 2
       # total tokens = sum of per-iteration surrogates.
    # K-07: 100+4*1 = 104; 200+4*2 = 208; total 312.
    assert doc["total_tokens"] == {"estimated": 312, "mode": "synthetic"}


def test_bad_final_outcome_rejected():
    tr = Trajectory(task_id="t", policy="mock", sandbox_root="/sbx")
    tr.add_row(build_row(iteration=1, tool_calls=[], context_chars=0, phase="stop"))
    assert set(TERMINAL_OUTCOMES) == {"VERIFIED", "BUDGET_EXHAUSTED", "STALLED:NOOP",
                                      "STALLED:BUDGET", "DENIED_LOOP", "ERROR"}
    for bad in ("PENDING", "FAILED", "done"):
        try:
            tr.finalize(bad)
            assert False, f"expected ValueError for {bad}"
        except ValueError:
            pass


def test_document_validates_against_schema():
    tr = Trajectory(task_id="parse-config", policy="mock", sandbox_root="/sbx")
    tr.add_row(build_row(iteration=1, tool_calls=[{"name": "read_file", "args": {"path": "a.py"}}],
                     context_chars=10, files_read=["a.py"], phase="observe"))
    doc = tr.finalize("VERIFIED")
    jsonschema.validate(doc, SCHEMA)


def test_serialization_is_byte_deterministic():
       # I-002: identical inputs -> byte-identical trajectory text.
    def build():
        tr = Trajectory(task_id="parse-config", policy="mock", sandbox_root="/sbx")
        tr.add_row(build_row(iteration=1, tool_calls=[{"name": "read_file", "args": {"path": "a"}}],
                         context_chars=10, phase="observe"))
        tr.add_row(build_row(iteration=2, tool_calls=[{"name": "edit_file", "args": {}}],
                             context_chars=20, files_modified=["a"], phase="modify"))
        return tr.finalize("VERIFIED")
    a, b = build(), build()
    assert json.dumps(a, indent=2, sort_keys=True) == json.dumps(b, indent=2, sort_keys=True)
