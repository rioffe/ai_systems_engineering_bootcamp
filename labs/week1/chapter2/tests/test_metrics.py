"""T-05a / T-05b / T-08b -- metric math and the §21 aggregate.

T-05a (I-001): the §18 worked example is exact (TP=2, FP=2, FN=1; P=0.5; R=2/3;
F1 ≈ 0.571).  T-05b (I-007): the no-division-by-zero guards (P=None, R=None,
F1=0.0).  T-08b / I-012: ``aggregate`` rolls per-case rows into dataset-level
means (over the non-None / JUDGED rows), a per-tier recursion, and the R-12
failure-stage breakdown.
"""

import pytest

from rag_eval.metrics import retrieval_pr, aggregate, S18_EXPECTED, S18_RETRIEVED
from rag_eval.types import RunMetrics


def test_t05a_s18_worked_example_is_exact():
  tp, fp, fn, p, r, f1 = retrieval_pr(list(S18_EXPECTED), list(S18_RETRIEVED))
  assert (tp, fp, fn) == (2, 2, 1)
  assert p == 0.5
  assert pytest.approx(r) == 2 / 3
  assert pytest.approx(f1) == 0.5714285714285714


def test_t05b_empty_retrieved_precision_none_recall_or_f1_zero():
  # E-02: no retrieved -> P=None (TP+FP==0), R=0.0, F1=0.0.
  tp, fp, fn, p, r, f1 = retrieval_pr(["a"], [])
  assert p is None and r == 0.0 and f1 == 0.0
  # E-04: P+R==0 (no overlap and no extra) -> F1=0.0.
  _, _, _, p2, r2, f2 = retrieval_pr(["a"], ["b"])
  assert p2 == 0.0 and r2 == 0.0 and f2 == 0.0


def test_t05b_all_irrelevant_precision_zero():
  # E-03 context-pollution: every retrieved doc is irrelevant, P=0.0, R=0.0, F1=0.0.
  tp, fp, fn, p, r, f1 = retrieval_pr(["x"], ["a", "b", "c"])
  assert (tp, fp, fn) == (0, 3, 1)
  assert p == 0.0 and r == 0.0 and f1 == 0.0


def test_t08b_aggregate_computes_means_and_tier_breakdown():
  # Three SCORED rows + one PARTIAL (judge failed) + one ERROR (retrieval fault).
  r1 = RunMetrics(
    "a",
    "easy",
    retrieved=["a", "b"],
    expected=["a"],
    tp=1,
    fp=1,
    fn=0,
    precision=0.5,
    recall=1.0,
    f1=2.0 / 3.0,
    correct=True,
    supported=True,
    complete=True,
    unsupported_claims=0,
    total_factual_claims=2,
    status="SCORED",
  )
  r2 = RunMetrics(
    "b",
    "easy",
    retrieved=["c"],
    expected=["a", "b"],
    tp=0,
    fp=1,
    fn=2,
    precision=0.0,
    recall=0.0,
    f1=0.0,
    correct=False,
    supported=False,
    complete=False,
    unsupported_claims=1,
    total_factual_claims=3,
    status="SCORED",
  )
  # PARTIAL: judge failed -> retrieval metrics still recorded, verdict fields None.
  r3 = RunMetrics(
    "c",
    "multi",
    retrieved=["a"],
    expected=["b"],
    tp=0,
    fp=1,
    fn=1,
    precision=0.0,
    recall=0.0,
    f1=0.0,
    correct=None,
    supported=None,
    complete=None,
    failure_stage="judging",
    status="PARTIAL",
  )
  # ERROR at retrieval stage: no meaningful retrieval recorded -> P/R/F1 None.
  r4 = RunMetrics(
    "d",
    "multi",
    expected=["x"],
    correct=None,
    supported=None,
    complete=None,
    failure_stage="retrieval",
    status="ERROR",
  )
  agg = aggregate([r1, r2, r3, r4])

  assert agg.n_cases == 4
  assert pytest.approx(agg.precision) == (0.5 + 0.0 + 0.0) / 3  # None excluded
  assert pytest.approx(agg.recall) == (1.0 + 0.0 + 0.0) / 3
  assert pytest.approx(agg.f1) == (2.0 / 3.0 + 0.0 + 0.0) / 3
  assert pytest.approx(agg.answer_accuracy) == 0.5  # 1 correct / 2 JUDGED rows
  assert pytest.approx(agg.hallucination_rate) == 1 / 5  # 1 unsupported / 5 total
  assert set(agg.by_tier) == {"easy", "multi"}
  assert agg.by_tier["easy"].n_cases == 2
  # R-10/I-012: by-tier aggregate recurses the same formula
  assert pytest.approx(agg.by_tier["easy"].answer_accuracy) == 0.5
  # R-12 failure breakdown (ok rows counted as "ok")
  assert set(agg.failure_breakdown) >= {"retrieval", "judging", "ok"}
  assert agg.failure_breakdown["ok"] == 2


def test_t08b_empty_aggregate_is_safe():
  agg = aggregate([])
  assert agg.n_cases == 0
  assert agg.hallucination_rate == 0.0  # I-007 no-div-by-zero
  assert agg.answer_accuracy == 0.0
  assert agg.by_tier == {} and agg.failure_breakdown == {}
