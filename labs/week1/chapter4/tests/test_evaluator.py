# pyright: reportMissingImports=false

from types import SimpleNamespace

from rag_eval.dataset import EvalCase
from rag_eval.evaluator import DeterministicChecks, evaluate_case, map_verdict


def test_status_mapping_preserves_ch3_status():
    assert map_verdict({"status": "PARTIAL"})["status"] == "FAIL"
    assert map_verdict({"status": "PARTIAL"})["ch3_status"] == "PARTIAL"


def test_parse_blocked_skips_judge_semantics():
    case = EvalCase("q", "question", "answer", ["c"], "easy", [])
    result = SimpleNamespace(parsed_answer=None, retrieved_chunks=["c"], verdict={"status": "SCORED"}, failure_stage=None)
    row = evaluate_case(case, result)
    assert row.verdict["status"] == "PARSE_BLOCKED"
    assert row.failure_classification == "PARSING_FAILURE"


def test_deterministic_checks_citation_membership():
    result = SimpleNamespace(parsed_answer={"citations": [{"chunk_id": "missing"}]}, retrieved_chunks=["c"])
    checks = DeterministicChecks().check(result)
    assert checks[0]["passed"]
    assert not checks[1]["passed"]
