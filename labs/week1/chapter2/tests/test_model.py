"""C-05 (model.py) -- the single probabilistic role: answer generation.

T-08/T-14/R-15: the ``MockLLM`` is a deterministic, offline, bitwise-reproducible
double that needs no Ollama and no network; its answer cites only doc ids present in
the context (grounded, I-003) and validates against the answer schema (I-010). The
``OllamaLLM`` real backend routes through a network-stubbed transport (httpx
MockTransport, no live daemon -- K-04/I-011) and maps Ollama usage counts. Failure
semantics: a parse/validation-exhausted generation yields ``Answer(status="ERROR")``
and never an unvalidated dict; an unreachable/unpulled model surfaces as a fatal
``OllamaError``/``ModelNotFoundError`` the CLI maps to an exit code (E-11/E-12).
"""

import json

import httpx
import pytest
from rag_eval.model import (
    MockLLM,
    ModelNotFoundError,
    OllamaClient,
    OllamaError,
    OllamaLLM,
    model_not_found_error,
)

from rag_eval.types import Usage


# ---------------------------------------------------------------- MockLLM -- offline double
def test_mock_llm_produces_a_schema_valid_grounded_answer():
    ctx = "[001]\nthe hotel limit is five thousand dollars\n\n[002]\nvisa needs two photos\n\n"
    answer = MockLLM().generate(system="S", context=ctx, question="hotel limit?")
    assert answer.status == "COMPLETED"
    assert answer.confidence >= 0.0 and answer.confidence <= 1.0
    assert set(answer.sources) <= {"001", "002"}, (
        "sources must be a subset of context ids"
    )
    assert len(answer.text.strip()) >= 1


def test_mock_llm_empty_context_cannot_answer():
    answer = MockLLM().generate(system="S", context="", question="anything?")
    assert answer.status == "COMPLETED"
    assert answer.sources == []
    assert answer.confidence == 0.0
    assert "cannot answer" in answer.text.lower()


def test_mock_llm_is_bitwise_reproducible_for_a_fixed_context():
    ctx = "[017]\nthe per-diem is one thousand dollars\n\n"
    a = MockLLM().generate(system="S", context=ctx, question="per-diem?")
    b = MockLLM(seed=42).generate(system="S", context=ctx, question="per-diem?")
    assert a.text == b.text and a.sources == b.sources and a.confidence == b.confidence


def test_mock_llm_hallucination_inserts_a_foreign_citation():
    ctx = "[001]\nthe hotel limit is five thousand dollars\n\n"
    answer = MockLLM(hallucinate=True).generate(
        system="S", context=ctx, question="hotel?"
    )
    assert answer.status == "COMPLETED"
    # A claim grounded in a doc id that is NOT in the context (E-08 / T-08a): the
    # harness must later strip this and force supported=False.
    assert "HALL-01" in answer.sources
    assert "HALL-01" not in ctx


def test_generation_exhausts_to_error_never_releases_unvalidated():
    # A "model" that always emits junk: after max_retries the generate returns an
    # ERROR answer, not an unvalidated object (E-07 / I-010).
    class AlwaysBadModel(MockLLM):
        def __init__(self):
            super().__init__()
            self._always_bad = True

    bad = AlwaysBadModel()
    answer = bad.generate(system="S", context="[001]\ntext\n\n", question="q?")
    assert answer.status == "ERROR"
    assert answer.sources == []


# ---------------------------------------------------------------- OllamaLLM -- real, transport-stubbed
def test_ollama_llm_maps_usage_and_answer_over_mock_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=json.dumps(
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "answer": "the limit is 1000 dollars",
                                "confidence": 0.8,
                                "sources": ["001"],
                            }
                        ),
                    },
                    "prompt_eval_count": 12,
                    "eval_count": 7,
                }
            ).encode("utf-8"),
        )

    client = OllamaClient(base="http://x", transport=httpx.MockTransport(handler))
    llm = OllamaLLM("qwen3.8:27b-mlx", client=client)
    answer = llm.generate(
        system="S", context="[001]\nlimit 1000 dollars\n\n", question="limit?"
    )
    assert answer.status == "COMPLETED"
    assert answer.text == "the limit is 1000 dollars"
    assert answer.confidence == 0.8
    assert answer.sources == ["001"]
    assert answer.usage == Usage(12, 7)
    assert llm.model_id == "qwen3.8:27b-mlx"


def test_ollama_llm_surface_model_not_found_error():
    # E-12: an unpulled model is a fatal backend error with the pull hint (T-18 analog).
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b'{"error": "model not found"}')

    client = OllamaClient(base="http://x", transport=httpx.MockTransport(handler))
    llm = OllamaLLM("ghost", client=client)
    with pytest.raises(ModelNotFoundError):
        llm.generate(system="S", context="x", question="q?")
    exc_ctx = model_not_found_error("ghost")
    assert "ollama pull ghost" in exc_ctx or "ghost" in exc_ctx


def test_discovery_lists_pulled_models_over_mock_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=json.dumps(
                {"models": [{"name": "qwen3.8:27b-mlx"}, {"name": "llama3.2:3b"}]}
            ).encode("utf-8"),
        )

    client = OllamaClient(base="http://x", transport=httpx.MockTransport(handler))
    assert set(client.list_models()) >= {"qwen3.8:27b-mlx", "llama3.2:3b"}


def test_ollama_unreachable_raises_ollama_error():
    # E-11: an unreachable daemon is a transport fault the caller treats as a fallback.
    client = OllamaClient(base="http://127.0.0.1:1", timeout_s=0.3)
    with pytest.raises(OllamaError):
        client.list_models()
