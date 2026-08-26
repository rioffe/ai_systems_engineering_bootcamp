"""C-07 metrics (R-07/08/09/12) -- pure, headless, deterministic.

Two levels of metric, both on the deterministic boundary (stdlib + ``types`` only; no LLM,
no network -- I-009 / T-02):

* ``retrieval_pr(expected, retrieved)`` decomposes TP/FP/FN (the §18 definition) and
  derives ``Precision = TP/(TP+FP)``, ``Recall = TP/(TP+FN)``, ``F1 = 2PR/(P+R)`` with the
  no-division-by-zero guards (I-007: P=None when TP+FP==0; R=None when TP+FN==0;
  F1=0.0 when P+R=0).
* ``aggregate(rows)`` rolls per-case ``RunMetrics`` into a dataset-level
   ``AggregateMetrics``: means over the rows that contribute, hallucination rate over the
  JUDGED rows, a per-tier recursion (I-012), and the R-12 failure-stage breakdown that
  distinguishes "did retrieval fail" from "did the model fail to use what it was given".
"""

from __future__ import annotations

from .types import AggregateMetrics, RunMetrics

# The §18 worked example, pinned by T-05/I-001 (T-05a):
#   expected = {D3, D17, D42}; retrieved = [D3, D17, D88, D91]
#    => TP=2, FP=2, FN=1, P=0.50, R=2/3, F1=2 PR/(P+R) ~= 0.571.
S18_EXPECTED = ("D3", "D17", "D42")
S18_RETRIEVED = ("D3", "D17", "D88", "D91")


def retrieval_pr(expected, retrieved):
    """Return ``(tp, fp, fn, precision, recall, f1)`` (C-07 / §18, I-001/I-007).

    ``precision`` is None when TP+FP==0 (E-02/E-03); ``recall`` is None when TP+FN==0
    (E-02); ``f1`` is 0.0 when P+R==0 (E-04) or when either of P/R is None.
    """
    exp = set(expected)
    ret = set(retrieved)
    tp = len(exp & ret)
    fp = len(ret - exp)
    fn = len(exp - ret)

    if tp + fp == 0:
        precision = None
    else:
        precision = tp / (tp + fp)
    if tp + fn == 0:
        recall = None
    else:
        recall = tp / (tp + fn)

    p_val = precision if precision is not None else 0.0
    r_val = recall if recall is not None else 0.0
    denom = p_val + r_val
    if denom == 0.0:
        f1 = 0.0
    else:
        f1 = 2.0 * p_val * r_val / denom
    return tp, fp, fn, precision, recall, f1


def _mean_non_null(values):
    """Mean over the non-None values; an empty set averages to 0.0 (I-007)."""
    nums = [v for v in values if v is not None]
    if not nums:
        return 0.0
    return sum(nums) / len(nums)


def _accuracy(rows):
    """Mean of ``correct`` over the JUDGED rows (R-08; a PARTIAL/ERROR row is None)."""
    judged = [r for r in rows if r.correct is not None]
    if not judged:
        return 0.0
    return sum(1 for r in judged if r.correct) / len(judged)


def _hallucination_rate(rows):
    """§20 / R-09 over the JUDGED rows: sum(unsupported)/sum(total), guarded I-007.

    A JUDGED row is one whose judge produced a verdict (``correct`` is not None); the
    no-division-by-zero guard yields 0.0 when the denominators sum to 0.
    """
    judged = [r for r in rows if r.correct is not None]
    total = sum(r.total_factual_claims for r in judged)
    if total == 0:
        return 0.0
    unsupported = sum(r.unsupported_claims for r in judged)
    return unsupported / total


def _failure_breakdown(rows):
    """R-12 fault-stage counts; a fully-succeeded (SCORED) row is recorded as ``ok``.

    ``failure_stage`` names *where* a non-terminal fault terminated (retrieval /
    context / generation / judging / cancelled); a SCORED row has ``failure_stage=None``
    and is counted under ``ok`` so the operator sees the full split.
    """
    counts = {}
    for r in rows:
        key = r.failure_stage if r.failure_stage is not None else "ok"
        counts[key] = counts.get(key, 0) + 1
    return counts


def _build(rows, tier_label=None):
    """Build an ``AggregateMetrics`` over ``rows`` (``tier_label`` makes it recursive)."""
    if tier_label is None:
        by_tier = {}
        for tier in sorted({r.tier for r in rows}):
            sub = [r for r in rows if r.tier == tier]
            by_tier[tier] = _build(sub, tier_label=tier)
    else:
        by_tier = {}
    return AggregateMetrics(
        n_cases=len(rows),
        precision=_mean_non_null([r.precision for r in rows]),
        recall=_mean_non_null([r.recall for r in rows]),
        f1=_mean_non_null([r.f1 for r in rows]),
        answer_accuracy=_accuracy(rows),
        hallucination_rate=_hallucination_rate(rows),
        failure_breakdown=_failure_breakdown(rows),
        by_tier=by_tier,
    )


def aggregate(rows):
    """Aggregate per-case ``RunMetrics`` into a dataset-level report (C-07 / §21).

    Precision/recall/f1 means are over the rows whose value is non-None; accuracy and
    hallucination rate are over the JUDGED rows (I-007); ``by_tier`` recurses one level
    per §17 tier present (I-012); ``failure_breakdown`` is the R-12 fault-stage split.
    """
    return _build(list(rows))


__all__ = [
    "AggregateMetrics",
    "RunMetrics",
    "aggregate",
    "retrieval_pr",
]
