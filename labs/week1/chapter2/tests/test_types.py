"""T-01 / T-01a -- record types (C-01/C-04/C-07) and the §15 grounding contract.

The dataclasses are the shared, headless contract the whole system agrees on. These
tests pin their invariants: non-empty ids, budget/truncation flags tier correctly, and
the terminal-status vocabulary (§3.1) is fixed.
"""

import pytest

from rag_eval.types import (
    AggregateMetrics,
    Answer,
    Context,
    Document,
    Question,
    RunMetrics,
    ScoredDoc,
    Usage,
    Verdict,
)


def test_t01_document_requires_nonempty_id():
    with pytest.raises(ValueError):
        Document(doc_id="", text="x")


def test_t01_document_accepts_domain():
    d = Document(doc_id="001", text="some text", domain="policy")
    assert d.doc_id == "001" and d.domain == "policy"


def test_t01_scoreddoc_score_and_rank_bounds():
    doc = Document("001", "t")
    with pytest.raises(ValueError):
        ScoredDoc(doc, score=-1.0, rank=1)
    with pytest.raises(ValueError):
        ScoredDoc(doc, score=0.3, rank=0)
    ok = ScoredDoc(doc, score=0.3, rank=1)
    assert ok.rank == 1 and ok.doc.doc_id == "001"


def test_t01_question_tier_must_be_known():
    with pytest.raises(ValueError):
        Question("q1", "q", "a", ["001"], tier="impossible")
    q = Question("q1", "q", "a", ["001"], tier="distractor")
    assert q.tier == "distractor" and "distractor" in Question.TIERS


def test_t01_scored_context_empty_flag():
    doc = Document("001", "abcde")
    ctx = Context(
        docs=[ScoredDoc(doc, 1.0, 1)],
        prompt="[001]\nabcde",
        provenance=["001"],
        tokens=3,
        truncated=False,
    )
    assert not ctx.empty
    empty = Context(docs=[], prompt="", provenance=[], tokens=0, truncated=False)
    assert empty.empty


def test_t01_answer_defaults_completed():
    a = Answer(q_id="q1", text="42 dollars", confidence=0.8)
    assert a.status == "COMPLETED" and a.sources == [] and a.usage.total_tokens == 0


def test_t01_usage_total_is_sum():
    u = Usage(3, 5)
    assert u.total_tokens == 8
    with pytest.raises(ValueError):
        Usage(-1, 0)


def test_t01_verdict_defaults_judged():
    v = Verdict("q1", True, True, True, [], 0, "ok")
    assert v.status == "JUDGED" and v.total_factual_claims == 0


def test_t01_runmetrics_defaults():
    rm = RunMetrics(q_id="q1", tier="easy")
    assert rm.status == "SCORED" and rm.failure_stage is None and rm.tp == 0


def test_t01_aggregate_fields_present():
    ag = AggregateMetrics(
        n_cases=0,
        precision=0.0,
        recall=0.0,
        f1=0.0,
        answer_accuracy=0.0,
        hallucination_rate=0.0,
    )
    assert set(ag.failure_breakdown) == set() and set(ag.by_tier) == set()
