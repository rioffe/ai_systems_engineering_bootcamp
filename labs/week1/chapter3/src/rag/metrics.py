"""Retrieval and generation metrics -- pure, LLM/network-free.

Implements C-11 / R-11 / R-12 / I-001 / I-007 from SPEC.md:
- retrieval: precision@k, recall@k, MRR@k, AP, MAP, NDCG@k
- generation: faithfulness, completeness, citation_quality
- aggregate over non-None rows into TierMetrics / AggregateMetrics.

All math obeys the no-division-by-zero guards (I-007):
   precision=None when |R_k|=0
   recall=None      when |G|=0
   mrr=0.0          when no relevant item within top-k
   ndcg=None        when IDCG=0
   faithfulness/completeness/citation_quality = 0.0 when denominator is 0
   a row with no retrieval output contributes nothing to a mean.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Sequence

from rag.types import AggregateMetrics, RunMetrics

# -- retrieval ----------------------------------------------------------------


def _top_k(retrieved: Sequence[str], k: int) -> list[str]:
    if k <= 0 or not retrieved:
        return []
    return list(retrieved[:k])


def precision(relevant: set[str], retrieved: Sequence[str], k: int) -> float | None:
    # precision@k = |G ∩ R_k| / |R_k|; None when |R_k| == 0 (I-007).
    rk = _top_k(retrieved, k)
    if not rk:
        return None
    hits = len(relevant.intersection(rk))
    if hits == 0:
        return 0.0
    return hits / len(rk)


def recall(relevant: set[str], retrieved: Sequence[str], k: int) -> float | None:
    # recall@k = |G ∩ R_k| / |G|; None when |G| == 0 (I-007).
    if not relevant:
        return None
    rk = _top_k(retrieved, k)
    hits = len(relevant.intersection(rk))
    if hits == 0:
        return 0.0
    return hits / len(relevant)


def mrr(relevant: set[str], retrieved: Sequence[str], k: int) -> float:
    # mrr@k = 1 / rank(first relevant) within top-k; 0.0 if none (I-007).
    rk = _top_k(retrieved, k)
    for i, item in enumerate(rk, start=1):
        if item in relevant:
            return 1.0 / i
    return 0.0


def ap(relevant: set[str], retrieved: Sequence[str], k: int) -> float | None:
    # ap_q = (1/|G|) * sum_{i: R_i in G} precision@i; None when |G| == 0 (I-007).
    if not relevant:
        return None
    rk = _top_k(retrieved, k)
    num = 0.0
    hits = 0
    for i, item in enumerate(rk, start=1):
        if item in relevant:
            hits += 1
            num += hits / i
    return num / len(relevant)


# Back-compat alias
average_precision = ap


def ndcg(relevant: set[str], retrieved: Sequence[str], k: int) -> float | None:
    # ndcg@k = dcg@k / idcg@k; None when idcg == 0 (I-007).
    if not relevant:
        return None
    rk = _top_k(retrieved, k)
    dcg = 0.0
    for i, item in enumerate(rk, start=1):
        if item in relevant:
            dcg += 1.0 / math.log2(i + 1)
    # IDCG: |G| items at ranks 1..min(|G|, k).
    ideal_n = min(len(relevant), len(rk)) if rk else len(relevant)
    if ideal_n == 0:
        return None
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_n + 1))
    if idcg == 0.0:
        return None
    return dcg / idcg


# -- generation ---------------------------------------------------------------


def _norm(s: str) -> str:
    # lowercase + collapse whitespace / non-alphanumerics for reflected-match.
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def faithfulness(
    total_factual_claims: int | None = None,
    unsupported_claims: list[str] | None = None,
    *,
    supported_claims: int | None = None,
    total: int | None = None,
) -> float:
    # faithfulness = supported / total_factual_claims; 0.0 when total == 0 (I-007).
    # F-005: supported = total - len(unsupported), recomputed after Citer recount.
    t = total_factual_claims
    if t is None:
        t = total
    if t is None or t == 0:
        return 0.0
    if supported_claims is None:
        u = unsupported_claims or []
        supported = t - len(u)
    else:
        supported = supported_claims
    if supported <= 0:
        return 0.0
    return supported / t


def completeness(
    reflected_set: Iterable[str],
    gold_facts: list[str],
    *,
    answer_text: str | None = None,
) -> float:
    # completeness = |reflected gold_facts| / |gold_facts|; 0.0 when |gold| == 0.
    # F-006: a fact is "reflected" iff its normalized tokens subset of a gold_fact.
    if not gold_facts:
        return 0.0
    reflected = {_norm(s) for s in reflected_set}
    if answer_text is not None:
        reflected.add(_norm(answer_text))
    hit = 0
    for g in gold_facts:
        gold_norm = _norm(g)
        gold_tokens = set(gold_norm.split())
        for ref in reflected:
            ref_tokens = set(ref.split())
            # a gold_fact is reflected when all its tokens appear in some reflection
            if gold_tokens and gold_tokens.issubset(ref_tokens):
                hit += 1
                break
    return hit / len(gold_facts)


def citation_quality(total: int, relevant: int) -> float:
    # citation_quality = relevant / total; 0.0 when total == 0 (I-007).
    if total == 0:
        return 0.0
    return relevant / total


# -- aggregation --------------------------------------------------------------


def aggregate(rows: list[RunMetrics], k: int = 5) -> AggregateMetrics:
    # Aggregate non-None per-row metrics; compute unset per-row metrics from
    # expected (ground truth) + retrieved first.
    agg = AggregateMetrics()
    for rm in rows:
        if rm.precision is None:
            rm.precision = precision(set(rm.expected), rm.retrieved, k)
        if rm.recall is None:
            rm.recall = recall(set(rm.expected), rm.retrieved, k)
        if rm.mrr is None:
            rm.mrr = mrr(set(rm.expected), rm.retrieved, k)
        if rm.ap is None:
            rm.ap = ap(set(rm.expected), rm.retrieved, k)
        if rm.ndcg is None:
            rm.ndcg = ndcg(set(rm.expected), rm.retrieved, k)
        agg.add(rm)
    return agg
