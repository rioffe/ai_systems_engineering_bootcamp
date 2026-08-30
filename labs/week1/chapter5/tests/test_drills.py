# pyright: reportMissingImports=false
from research_agent.drills import DRILLS, run_drill


def test_all_ten_drills_are_registered():
    expected = {"search_timeout", "empty_results", "malformed_arguments", "retrieval_failure", "duplicate_searches", "contradictory_sources", "low_quality_sources", "infinite_loop", "max_steps_exhaustion", "unauthorized_tool_call"}
    assert set(DRILLS) == expected


def test_drill_emits_four_question_report():
    report = run_drill("empty_results")
    assert report["drill_report_version"] == "0.1"
    assert all(report[field] for field in ("model_behavior", "runtime_behavior", "expected_behavior", "instrumentation"))
