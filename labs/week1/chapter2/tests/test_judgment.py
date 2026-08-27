"""C-06 (judgment.py) -- the second probabilistic role: LLM-as-judge (R-06).

The ``MockJudge`` is a deterministic, offline double (R-14) that derives a
schema-valid verdict from the **ground truth** -- the intersection of the question's
``relevant_docs`` and the context's ``provenance``, plus the answer's citations --
so the automated suite measures the *metric math* (R-07/08/09) without a model.
The ``OllamaJudge`` real backend asks ``qwen3.8:27b-mlx`` to emit the verdict schema.
Hallucination math (I-007/R-09): a foreign citation counts as one unsupported claim out
of the total cited; an all-supported answer and a zero-claim answer both yield a 0.0 rate.
"""

import json

import httpx

from rag_eval.judgment import MockJudge, OllamaJudge
from rag_eval.model import OllamaClient
from rag_eval.types import Answer, Context, Question


def _ctx(provenance=("001", "002")):
    # A minimal Context; the MockJudge reads only provenance (grounding).
    return Context(
        docs=[], prompt="p", provenance=list(provenance), tokens=5, truncated=False
    )


def _q(relevant=("001",)):
    return Question(
        q_id="t1",
        question="what?",
        gold_answer="42 dollars",
        relevant_docs=list(relevant),
        tier="easy",
    )


# ---------------------------------------------------------------- MockJudge -- offline double
def test_all_supported_answer_has_zero_hallucination():
    ctx = _ctx(["001", "002"])
    ans = Answer(q_id="t1", text="ok", confidence=0.9, sources=["001", "002"])
    v = MockJudge().judge(question=_q(["001", "002"]), context=ctx, answer=ans)
    assert v.status == "JUDGED"
    assert v.supported is True
    assert v.complete is True
    assert v.correct is True
    assert v.unsupported_claims == []
    assert v.total_factual_claims == 2  # both citations are grounded claims


def test_foreign_citation_counts_as_an_unsupported_claim():
    # E-08 / T-08a: a citation of a doc id NOT in the context is one unsupported claim.
    ctx = _ctx(["001"])
    ans = Answer(q_id="t1", text="ok", confidence=0.5, sources=["001", "HALL-01"])
    v = MockJudge().judge(question=_q(["001"]), context=ctx, answer=ans)
    assert v.supported is False
    assert len(v.unsupported_claims) == 1
    assert v.total_factual_claims == 2  # 1 grounded + 1 foreign
    # hallucination rate == unsupported / total, exercised downstream in aggregate (T-08a).
    assert len(v.unsupported_claims) / v.total_factual_claims == 0.5


def test_zero_claim_answer_has_zero_total():
    # I-007: no citations -> total 0 -> the rate guard yields 0.0 (checked in aggregate).
    ctx = _ctx(["001"])
    ans = Answer(
        q_id="t1",
        text="I cannot answer from the provided documents.",
        confidence=0.0,
        sources=[],
    )
    v = MockJudge().judge(question=_q(["001"]), context=ctx, answer=ans)
    assert v.total_factual_claims == 0
    assert v.unsupported_claims == []
    assert v.correct is False  # nothing was retrieved to be correct about


def test_complete_reflects_ground_truth_retrieval():
    # complete is True only when every relevant doc is in the provenance.
    v_ok = MockJudge().judge(
        question=_q(["001", "002"]),
        context=_ctx(["001", "002"]),
        answer=Answer(q_id="t1", text="x", confidence=0.5, sources=["001", "002"]),
    )
    v_miss = MockJudge().judge(
        question=_q(["001", "002", "003"]),
        context=_ctx(["001", "002"]),
        answer=Answer(q_id="t1", text="x", confidence=0.5, sources=["001", "002"]),
    )
    assert v_ok.complete is True
    assert v_miss.complete is False
    assert v_miss.correct is False


def test_mock_judge_is_bitwise_reproducible():
    ctx = _ctx(["001"])
    ans = Answer(q_id="t1", text="ok", confidence=0.8, sources=["001"])
    a = MockJudge().judge(question=_q(["001"]), context=ctx, answer=ans)
    b = MockJudge().judge(question=_q(["001"]), context=ctx, answer=ans)
    assert (
        a.correct,
        a.supported,
        a.complete,
        a.total_factual_claims,
        list(a.unsupported_claims),
        a.rationale,
    ) == (
        b.correct,
        b.supported,
        b.complete,
        b.total_factual_claims,
        list(b.unsupported_claims),
        b.rationale,
    )


def test_judge_exhausts_to_error_status():
    # A judge that always emits junk -> Verdict(status="ERROR") (E-10).
    class BadJudge(MockJudge):
        def _raw(self, *_a, **_k):
            return "not json {"

    v = BadJudge().judge(
        question=_q(["001"]),
        context=_ctx(["001"]),
        answer=Answer(q_id="t1", text="x", confidence=0.5, sources=["001"]),
    )
    assert v.status == "ERROR"
    assert v.correct is None and v.supported is None and v.complete is None


# ---------------------------------------------------------------- OllamaJudge -- real, transport-stubbed
def test_ollama_judge_maps_verdict_over_mock_transport():
    verdict_json = json.dumps(
        {
            "correct": True,
            "supported": False,
            "complete": True,
            "unsupported_claims": ["cite 009"],
            "total_factual_claims": 3,
            "rationale": "partly",
        }
    )

    # Ollama's non-stream /api/chat envelope: the model's raw text lives in message.content.
    envelope = json.dumps(
        {
            "message": {"role": "assistant", "content": verdict_json},
            "prompt_eval_count": 4,
            "eval_count": 2,
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=envelope.encode("utf-8"))

    client = OllamaClient(base="http://x", transport=httpx.MockTransport(handler))
    judge = OllamaJudge("qwen3.8:27b-mlx", client=client)
    v = judge.judge(
        question=_q(["001"]),
        context=_ctx(["001"]),
        answer=Answer(q_id="t1", text="x", confidence=0.5, sources=["001"]),
    )
    assert v.status == "JUDGED"
    assert (v.correct, v.supported, v.complete) == (True, False, True)
    assert v.total_factual_claims == 3
    assert judge.model_id == "qwen3.8:27b-mlx"


def test_judge_clamps_unsupported_count_to_total_factual_claims():
    # s017 wrinkle: the model listed an unsupported claim but reported 0 total factual
    # claims -- numerator > denominator (I-007 violation). The total-function boundary
    # must lift the denominator so the hallucination rate stays in [0,1] and the flagged
    # claim is never silently dropped.
    verdict_json = json.dumps(
        {
            "correct": False,
            "supported": False,
            "complete": False,
            "unsupported_claims": ["The total applies (2800, 5000, 5850)"],
            "total_factual_claims": 0,
            "rationale": "no combined total offered",
        }
    )
    envelope = json.dumps({"message": {"role": "assistant", "content": verdict_json}})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=envelope.encode("utf-8"))

    client = OllamaClient(base="http://x", transport=httpx.MockTransport(handler))
    judge = OllamaJudge("gemma4:31b", client=client)
    v = judge.judge(
        question=_q(["001"]),
        context=_ctx(["001"]),
        answer=Answer(q_id="t1", text="I cannot answer", confidence=0.0, sources=[]),
    )
    assert v.status == "JUDGED"
    assert v.unsupported_claims == ["The total applies (2800, 5000, 5850)"]
    assert v.total_factual_claims == 1  # lifted from 0 to 1
    assert len(v.unsupported_claims) <= v.total_factual_claims  # I-007 invariant


def test_judge_consistent_verdict_is_untouched():
    # A self-consistent verdict (numerator <= denominator) must pass through unchanged.
    verdict_json = json.dumps(
        {
            "correct": True,
            "supported": False,
            "complete": True,
            "unsupported_claims": ["cite 009"],
            "total_factual_claims": 3,
            "rationale": "partly",
        }
    )
    envelope = json.dumps({"message": {"role": "assistant", "content": verdict_json}})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=envelope.encode("utf-8"))

    client = OllamaClient(base="http://x", transport=httpx.MockTransport(handler))
    v = OllamaJudge("qwen3.8:27b-mlx", client=client).judge(
        question=_q(["001"]),
        context=_ctx(["001"]),
        answer=Answer(q_id="t1", text="x", confidence=0.5, sources=["001"]),
    )
    assert v.total_factual_claims == 3
    assert len(v.unsupported_claims) <= v.total_factual_claims
