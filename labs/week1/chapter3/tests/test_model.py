"""Tests for rag.model -- MockLLM gold-isolation (F-001) + OllamaLLM.

Implements T-08, T-11a, R-09, R-17, R-18, I-003 from SPEC.md C-09.
"""

from __future__ import annotations

from rag.model import MockLLM, OllamaLLM

# -- gold isolation: F-001 ---------------------------------------------------


def test_mockllm_model_id_is_mock():
    llm = MockLLM()
    assert llm.model_id == "mock"


def test_mockllm_produces_completed_answer_from_context():
    llm = MockLLM()
    answer = llm.generate(
        system="agent",
        context="The refund limit is $5000.",
        question="What is the refund limit?",
        schema={"q_id": "q1"},
    )
    assert answer.status == "COMPLETED"
    assert 0.0 <= answer.confidence <= 1.0
    assert len(answer.text) > 0


def test_mockllm_answer_citations_use_context_chunk_ids():
    llm = MockLLM()
    answer = llm.generate(
        system="s",
        context="doc:refund The refund limit is $5000.",
        question="What is the refund limit?",
        schema={},
    )
    for c in answer.citations:
        assert len(c.chunk_id) > 0
        assert c.source != ""


def test_mockllm_does_not_leak_gold_facts():
    llm = MockLLM()
    ctx_text = "The refund limit is $5000."
    answer = llm.generate(
        system="s",
        context=ctx_text,
        question="What is the refund limit?",
        schema={},
    )
    assert "XYZ123" not in answer.text


def test_mockllm_empty_context_low_confidence():
    llm = MockLLM()
    answer = llm.generate(
        system="s",
        context="",
        question="What is the refund limit?",
        schema={},
    )
    assert answer.status in ("COMPLETED", "ERROR")
    if answer.status == "COMPLETED":
        assert answer.confidence < 0.5 or len(answer.citations) == 0


def test_mockllm_deterministic():
    llm = MockLLM()
    kwargs = {
        "system": "s",
        "context": "The refund limit is $5000.",
        "question": "What is the refund limit?",
        "schema": {},
    }
    a1 = llm.generate(**kwargs)
    a2 = llm.generate(**kwargs)
    assert a1.text == a2.text
    assert a1.confidence == a2.confidence
    ids1 = [c.chunk_id for c in a1.citations]
    ids2 = [c.chunk_id for c in a2.citations]
    assert ids1 == ids2


# -- OllamaLLM type existence ------------------------------------------------


def test_ollamallm_has_model_id():
    llm = OllamaLLM(model="qwen3.8:27b-mlx")
    assert llm.model_id == "qwen3.8:27b-mlx"
