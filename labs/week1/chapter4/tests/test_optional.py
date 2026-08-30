# pyright: reportMissingImports=false

from rag_eval.judge_check import judge_check
from rag_eval.new_case import scaffold_case
from rag_eval.pair import run_pair


def test_judge_check_reports_disagreement():
    report = judge_check(
        {"cases": [{"case_id": "q", "verdict": {"correct": True}}]}, {"q": {"correct": False}}
    )
    assert report["agreement"]["correct"] == 0
    assert report["disagreements"]


def test_pair_tie_is_in_denominator():
    rows = [
        {"case_id": "1", "metrics": {"accuracy": 1}},
        {"case_id": "2", "metrics": {"accuracy": 1}},
    ]
    report = run_pair(rows, rows)
    assert report["comparisons"] == 2 and report["win_rate_a"] == 0


def test_new_case_uses_sentinels():
    case = scaffold_case({"question": "q"}, "id")
    assert case["reference_answer"] == "REPLACE_ME"
    assert case["source"] == "production"
