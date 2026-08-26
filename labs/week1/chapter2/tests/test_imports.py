"""T-02 / T-14 (core half) -- the LLM-in-exactly-two-places invariant + offline posture.

T-02 / I-009: the deterministic boundary modules (retrieval, context, metrics, corpus,
    types, schemas) contain NO reference to the LLM/provider -- no `httpx` import, no
    `OllamaClient` / `OllamaLLM` / `OllamaJudge` / `MockLLM` / `MockJudge` identifier, and no
    `from .model` / `from .judgment` import. Those live only in the (not-yet-built)
    `model.py` / `judgment.py` -- the single seam through which everything is swappable.
T-14 / K-01 (core half): importing the deterministic core pulls no network dependency into
    `sys.modules`; and the deterministic pipeline (retrieve -> context -> metrics) runs
    end-to-end with no Ollama and no network.
"""

import importlib
import re
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src" / "rag_eval"

DETERMINISTIC = [
    "retrieval.py",
    "context.py",
    "metrics.py",
    "corpus.py",
    "types.py",
    "schemas.py",
]
FORBIDDEN_IMPORT = re.compile(r"^\s*(?:import|from)\s+httpx\b", re.M)
FORBIDDEN_MODEL_IMPORT = re.compile(r"^\s*from\s+\.(?:model|judgment)\b", re.M)
FORBIDDEN_IDENTIFIERS = [
    "OllamaClient",
    "OllamaLLM",
    "OllamaJudge",
    "MockLLM",
    "MockJudge",
]
VENDOR_SDKS = ["openai", "anthropic", "cohere", "azure.ai", "google.generativeai"]


def _source(name):
    p = SRC / name
    assert p.exists(), f"missing deterministic module {name}"
    return p.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", DETERMINISTIC)
def test_t02_no_httpx_or_model_import(name):
    text = _source(name)
    assert not FORBIDDEN_IMPORT.search(text), f"{name} imports httpx"
    assert not FORBIDDEN_MODEL_IMPORT.search(text), (
        f"{name} imports a probabilistic module"
    )


@pytest.mark.parametrize("name", DETERMINISTIC)
def test_t02_no_provider_identifiers_in_code(name):
    text = _source(name)
    for ident in FORBIDDEN_IDENTIFIERS:
        pat = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(ident) + r"(?![A-Za-z0-9_])")
        assert not pat.search(text), f"{name} references {ident}"


@pytest.mark.parametrize("name", DETERMINISTIC)
def test_t02_no_vendor_sdk_named(name):
    text = _source(name)
    for v in VENDOR_SDKS:
        pat = re.compile(r"(?<![\w.])" + re.escape(v) + r"(?![\w.])")
        assert not pat.search(text), f"{name} names vendor SDK {v}"


def test_t14_core_imports_do_not_load_httpx():
    # Importing the deterministic core must not *pull in* a network dependency.
    before = set(sys.modules)
    for mod in (
        "rag_eval.types",
        "rag_eval.retrieval",
        "rag_eval.context",
        "rag_eval.metrics",
        "rag_eval.corpus",
        "rag_eval.schemas",
    ):
        importlib.import_module(mod)
    added = set(sys.modules) - before
    assert not any("httpx" in m for m in added), (
        f"core pulled in a network dep: {added}"
    )


def test_t14_offline_deterministic_pipeline_runs_with_no_network():
    # retrieve -> context -> metrics end-to-end, no Ollama, no network (K-01 / T-14).
    from rag_eval.context import build_context
    from rag_eval.metrics import aggregate, retrieval_pr
    from rag_eval.retrieval import BM25Retriever
    from rag_eval.types import Document, RunMetrics

    docs = [
        Document("001", "the reimbursement limit for hotels is five thousand dollars"),
        Document("002", "visa applications require two photos and a processing fee"),
        Document("003", "the hotel per-diem cap for new hires is one thousand dollars"),
    ]
    retriever = BM25Retriever(docs)
    retrieved = [
        sd.doc.doc_id for sd in retriever.search("hotel reimbursement limit", 3)
    ]
    ctx = build_context(
        retriever.search("hotel reimbursement limit", 3), token_budget=2000
    )
    tp, fp, fn, p, r, f1 = retrieval_pr(["001", "003"], retrieved)
    row = RunMetrics(
        "q1",
        "easy",
        retrieved=retrieved,
        expected=["001", "003"],
        tp=tp,
        fp=fp,
        fn=fn,
        precision=p,
        recall=r,
        f1=f1,
        context_tokens=ctx.tokens,
        truncated=ctx.truncated,
    )
    agg = aggregate([row])
    assert agg.n_cases == 1
    assert "ok" in agg.failure_breakdown
    assert 0.0 <= (agg.precision or 0.0) <= 1.0
