# pyright: reportAttributeAccessIssue=false

from types import SimpleNamespace

from rag_eval.metrics import (
    aggregate_metrics,
    average_precision,
    case_metrics,
    mrr_at_k,
    ndcg_at_k,
    near_rank_percentile,
    precision_at_k,
    recall_at_k,
)


def result(**kwargs):
    values = {
        "retrieved_chunks": ["a", "x", "b"],
        "parsed_answer": {},
        "latency_ms": 1.0,
        "cost_usd": 0.2,
    }
    values.update(kwargs)
    return SimpleNamespace(**values)


def test_retrieval_metrics_and_percentile():
    assert precision_at_k({"a", "b"}, ["a", "x", "b"], 3) == 2 / 3
    assert recall_at_k({"a", "b"}, ["a", "x", "b"], 2) == 0.5
    assert mrr_at_k({"b"}, ["a", "b"], 2) == 0.5
    assert average_precision({"a", "b"}, ["a", "x", "b"], 3) == (1 + 2 / 3) / 2
    assert ndcg_at_k({"a"}, ["x", "a"], 2) > 0
    assert near_rank_percentile(list(range(1, 21)), 95) == 19


def test_zero_rules_and_case_metrics():
    empty = SimpleNamespace(relevant_chunks=[], gold_facts=[])
    row = case_metrics(empty, result(parsed_answer=None, verdict={}), 0)
    assert row["accuracy"] == 0.0
    assert row["precision_at_k"] == 0.0
    assert row["recall_at_k"] == 0.0
    assert row["groundedness"] == 1.0
    assert row["completeness"] == 1.0
    assert row["hallucination_rate"] == 0.0


def test_aggregate_has_sorted_categories_and_difficulty():
    rows = [
        {
            "category": "z",
            "difficulty": "hard",
            "accuracy": 1,
            "precision_at_k": 1,
            "recall_at_k": 1,
            "mrr_at_k": 1,
            "map": 1,
            "ndcg_at_k": 1,
            "groundedness": 1,
            "completeness": 1,
            "hallucination_rate": 0,
            "latency_ms": 2,
            "cost_usd": 1,
        },
        {
            "category": "a",
            "difficulty": "easy",
            "accuracy": 0,
            "precision_at_k": 0,
            "recall_at_k": 0,
            "mrr_at_k": 0,
            "map": 0,
            "ndcg_at_k": 0,
            "groundedness": 0,
            "completeness": 0,
            "hallucination_rate": 1,
            "latency_ms": 4,
            "cost_usd": None,
        },
    ]
    aggregate = aggregate_metrics(rows, categories=["z", "a"], difficulties=["hard", "easy"])
    assert list(aggregate["by_category"]) == ["a", "z"]
    assert aggregate["accuracy"] == 0.5
    assert set(aggregate["by_difficulty"]) == {"easy", "hard"}
