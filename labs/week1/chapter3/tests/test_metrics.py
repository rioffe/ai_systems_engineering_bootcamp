"""Tests for rag.metrics -- the worked examples and no-division-by-zero guards.

Implements T-05a, T-05b, T-08a, T-08b (SPEC section 9.4 / 9.6).
"""

from __future__ import annotations

import pytest

from rag.metrics import (
    aggregate,
    ap,
    citation_quality,
    completeness,
    faithfulness,
    mrr,
    ndcg,
    precision,
    recall,
)
from rag.types import RunMetrics


def test_precision_recall_mrr_ndcg_worked_example():
    """T-05a: G={c1,c3,c5}, R_5=[c1,c8,c3,c9,c5], k=5."""
    G = {"c1", "c3", "c5"}
    R = ["c1", "c8", "c3", "c9", "c5"]
    # P@5 = 3/5 = 0.60
    assert precision(G, R, 5) == pytest.approx(0.6)
    # R@5 = 3/3 = 1.0
    assert recall(G, R, 5) == pytest.approx(1.0)
    # MRR@5 = 1/rank(c1) = 1.0
    assert mrr(G, R, 5) == pytest.approx(1.0)
    # NDCG@5 = 1.88685/2.13093 ~= 0.88547
    assert ndcg(G, R, 5) == pytest.approx(0.88547, rel=1e-4)


def test_ap_map_over_examples():
    """T-05b: q1 R=[r1,T,r3,T,r4,r5] G={r1,r3}; q2 R=[s1,s2,T] G={s2}."""
    q1_R = ["r1", "r2", "r3", "r4", "r5"]
    q2_R = ["s1", "s2"]
    q1_ap = ap({"r1", "r3"}, q1_R, 5)
    q2_ap = ap({"s2"}, q2_R, 5)
    # AP = (P@1 + P@3)/2  where P@1=1, P@3=2/3 -> (1 + 2/3)/2 = 0.83333
    assert q1_ap == pytest.approx(0.83333333333, rel=1e-9)
    assert q2_ap == pytest.approx(0.5, rel=1e-9)


def test_map_is_mean_of_aps():
    rows = [
        RunMetrics(
            q_id="q1", tier="easy", retrieved=["r1", "r2", "r3", "r4", "r5"], expected=["r1", "r3"]
        ),
        RunMetrics(q_id="q2", tier="easy", retrieved=["s1", "s2"], expected=["s2"]),
    ]
    agg = aggregate(rows)
    m = agg.means()
    assert m["mrr"] == pytest.approx(0.75, rel=1e-9)
    assert m["ap"] == pytest.approx(0.6666666, rel=1e-6)


def test_mrr_rank_beyond_k_is_zero():
    """F-014 / I-007: q3 has only relevant at rank 6, k=5 -> MRR@5=0.0."""
    G = {"x6"}
    R = ["a", "b", "c", "d", "e", "x6"]
    assert mrr(G, R, 5) == 0.0


def test_empty_retrieval_precision_is_none():
    G = {"c1"}
    assert precision(G, [], 5) is None
    assert recall(G, [], 5) == 0.0


def test_no_division_by_zero_faithfulness_zero_claims():
    """T-08a: total_factual_claims=0 -> faithfulness=0.0."""
    assert faithfulness(total_factual_claims=0, unsupported_claims=[]) == 0.0


def test_faithfulness_worked_example():
    """T-08a: total=4, unsupported=1 -> 3/4=0.75.
    F-005: supported = total - len(unsupported) (recomputed AFTER the Citer recount).
    """
    assert faithfulness(4, ["c2"]) == pytest.approx(0.75)
    # also accepts counts via total_factual_claims kw
    assert faithfulness(total_factual_claims=4, unsupported_claims=["c2"]) == pytest.approx(0.75)


def test_completeness_worked_example():
    """T-08a: 4 gold_facts, 3 reflected -> 3/4 = 0.75."""
    gold = ["A and B", "C and D", "E and F", "G"]
    reflected = ["a and b", "c and d", "E and F"]  # case-insensitive normalized match
    assert completeness(reflected_set=reflected, gold_facts=gold) == pytest.approx(0.75)
    # empty denominator
    assert completeness(reflected_set=gold, gold_facts=[]) == 0.0


def test_citation_quality_worked_example():
    """T-08a: 5 citations, 4 relevant -> 4/5 = 0.8."""
    assert citation_quality(total=5, relevant=4) == pytest.approx(0.8)
    assert citation_quality(total=0, relevant=0) == 0.0


def test_aggregate_by_tier_and_non_none_means():
    """T-08b / I-012: by_tier has one sub-aggregate per populated tier;
    means aggregate over non-None rows.
    """
    rows = [
        RunMetrics(q_id="q1", tier="easy", precision=1.0, recall=1.0, mrr=1.0, ndcg=1.0),
        RunMetrics(q_id="q2", tier="easy", precision=0.5, recall=0.5, mrr=0.5, ndcg=0.5),
        RunMetrics(q_id="q3", tier="multi", precision=None, recall=None, mrr=0.0, ndcg=None),
    ]
    agg = aggregate(rows)
    m = agg.means()
    # only q1, q2 contribute to precision/recall/ndcg (q3 is None for those)
    assert m["precision"] == pytest.approx(0.75)
    assert m["recall"] == pytest.approx(0.75)
    assert m["ndcg"] == pytest.approx(0.75)
    # mrr over q1(1.0), q2(0.5), q3(0.0) = 0.5
    assert m["mrr"] == pytest.approx(0.5)
    # by_tier: 'easy' has 2 rows, 'multi' has 1
    assert "easy" in agg.by_tier
    assert "multi" in agg.by_tier
    assert agg.by_tier["easy"].n == 2
    assert agg.by_tier["multi"].n == 1


def test_aggregate_by_capability_populated():
    """T-08b / I-012: by_capability has one sub-aggregate per TOGGLED stage;
    a disabled capability (on=False) yields no key. This is the case that was
    dead before run_case populated capability_flags.
        """
    rows = [
        RunMetrics(
            q_id="q1",
            tier="easy",
            precision=1.0,
            recall=1.0,
            capability_flags={"hybrid": True, "rerank": False, "expand": True},
            ),
        RunMetrics(
            q_id="q2",
            tier="easy",
            precision=0.5,
            recall=0.5,
            capability_flags={"hybrid": True, "rerank": True, "expand": False},
            ),
    ]
    agg = aggregate(rows)
    # Only ENABLED capabilities get a sub-aggregate; keys are '+<cap>'.
    assert set(agg.by_capability) == {"+hybrid", "+rerank", "+expand"}
    # '+hybrid' aggregates both rows (both had hybrid=True).
    assert agg.by_capability["+hybrid"].n == 2
    # '+rerank' aggregates only q2.
    assert agg.by_capability["+rerank"].n == 1
    # '+expand' aggregates only q1.
    assert agg.by_capability["+expand"].n == 1


def test_by_capability_empty_when_no_flags():
    """I-012: with no capability_flags, by_capability stays empty (the old
    dead-aggregation case); means are still computed over all rows.
        """
    rows = [RunMetrics(q_id="q1", tier="easy", precision=1.0, recall=1.0)]
    agg = aggregate(rows)
    assert agg.by_capability == {}
    assert agg.means()["precision"] == pytest.approx(1.0)
