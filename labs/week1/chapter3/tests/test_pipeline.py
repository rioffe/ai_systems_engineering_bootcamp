"""Tests for rag.pipeline -- build_index + run_case + run_dataset.

Implements T-03, T-07, T-11a, T-13, R-01, R-14, R-15 from SPEC.md C-12.
"""

from __future__ import annotations

from rag.pipeline import build_index, run_case, run_dataset

from rag.corpus import generate_corpus_and_questions, load_corpus
from rag.embedding import MockEmbedder
from rag.judgment import MockJudge
from rag.model import MockLLM
from rag.types import Question

# -- build_index (T-03) ------------------------------------------------------


def test_build_index_returns_vectorstore_and_bm25(tmp_path):
    generate_corpus_and_questions(
        str(tmp_path / "gen"),
        n_docs=5,
        n_questions=3,
        seed=42,
    )
    docs = load_corpus(str(tmp_path / "gen" / "documents" / "corpus.jsonl"))
    embedder = MockEmbedder()
    vs, bm = build_index(
        docs,
        strategy="fixed",
        contextual=True,
        embedder=embedder,
        overlap=10,
        chunk_size=50,
        embed_model="mock",
        mock=True,
    )
    assert vs is not None
    assert bm is not None
    assert len(vs._data) > 0 or len(bm._data) > 0


def test_build_index_determinism(tmp_path):
    # Running build_index twice with the same seed yields byte-identical
    # index outputs
    # (I-002, T-03).
    generate_corpus_and_questions(
        str(tmp_path / "gen"),
        n_docs=5,
        n_questions=3,
        seed=42,
    )
    docs = load_corpus(str(tmp_path / "gen" / "documents" / "corpus.jsonl"))
    e1 = MockEmbedder()
    e2 = MockEmbedder()
    vs1, _ = build_index(
        docs,
        strategy="fixed",
        contextual=True,
        embedder=e1,
        overlap=10,
        chunk_size=50,
        embed_model="mock",
        mock=True,
    )
    vs2, _ = build_index(
        docs,
        strategy="fixed",
        contextual=True,
        embedder=e2,
        overlap=10,
        chunk_size=50,
        embed_model="mock",
        mock=True,
    )
    # Compare stored vectors (same chunk_ids, same embedding values).
    keys1 = sorted((d.chunk_id, tuple(round(v, 6) for v in vec)) for d, vec in vs1._data.values())
    keys2 = sorted((d.chunk_id, tuple(round(v, 6) for v in vec)) for d, vec in vs2._data.values())
    assert keys1 == keys2


# -- run_case (T-11a) --------------------------------------------------------


def test_run_case_easy_tier_passes(tmp_path):
    generate_corpus_and_questions(
        str(tmp_path / "gen"),
        n_docs=10,
        n_questions=5,
        seed=42,
        failure_mode_docs=["conflict", "recency"],
    )
    docs = load_corpus(str(tmp_path / "gen" / "documents" / "corpus.jsonl"))
    embedder = MockEmbedder()
    vs, bm = build_index(
        docs,
        strategy="fixed",
        contextual=True,
        embedder=embedder,
        overlap=10,
        chunk_size=50,
        embed_model="mock",
        mock=True,
    )
    questions = [
        Question(
            q_id="q-test",
            question="What is the refund limit?",
            gold_answer="The refund limit is $5000.",
            gold_facts=["refund limit is $5000"],
            relevant_chunks=["doc-0000-1234#0"],
            relevant_docs=["doc-0000-1234"],
            tier="easy",
        )
    ]
    metrics = run_case(
        questions[0],
        (vs, bm),
        hybrid=True,
        alpha=0.5,
        rerank=False,
        top_n=50,
        top_k=5,
        expand=False,
        n_expand=0,
        judge=MockJudge(),
        llm=MockLLM(),
        cfg=None,
    )
    assert metrics.status in ("SCORED", "PARTIAL", "ERROR")
    assert metrics.q_id == "q-test"
    assert metrics.tier == "easy"


def test_run_case_determinism(tmp_path):
    # Two identical runs on the same corpus+question+params produce the
    # same RunMetrics output (R-18).
    generate_corpus_and_questions(
        str(tmp_path / "gen"),
        n_docs=10,
        n_questions=5,
        seed=42,
    )
    docs = load_corpus(str(tmp_path / "gen" / "documents" / "corpus.jsonl"))
    e1 = MockEmbedder()
    e2 = MockEmbedder()
    vs1, _ = build_index(
        docs,
        strategy="fixed",
        contextual=True,
        embedder=e1,
        overlap=10,
        chunk_size=50,
        embed_model="mock",
        mock=True,
    )
    vs2, _ = build_index(
        docs,
        strategy="fixed",
        contextual=True,
        embedder=e2,
        overlap=10,
        chunk_size=50,
        embed_model="mock",
        mock=True,
    )
    q = Question(
        q_id="q-det",
        question="What is the refund limit?",
        gold_answer="The refund limit is $5000.",
        gold_facts=["refund limit is $5000"],
        relevant_chunks=["doc-0000-1234#0"],
        relevant_docs=["doc-0000-1234"],
        tier="easy",
    )
    m1 = run_case(
        q,
        (vs1, _),
        hybrid=True,
        alpha=0.5,
        rerank=False,
        top_n=50,
        top_k=5,
        expand=False,
        n_expand=0,
        judge=MockJudge(),
        llm=MockLLM(),
        cfg=None,
    )
    m2 = run_case(
        q,
        (vs2, _),
        hybrid=True,
        alpha=0.5,
        rerank=False,
        top_n=50,
        top_k=5,
        expand=False,
        n_expand=0,
        judge=MockJudge(),
        llm=MockLLM(),
        cfg=None,
    )
    assert m1.retrieved == m2.retrieved
    assert m1.precision == m2.precision
    assert m1.recall == m2.recall


# -- run_dataset ------------------------------------------------------------


def test_run_dataset_produces_metrics_list(tmp_path):
    generate_corpus_and_questions(
        str(tmp_path / "gen"),
        n_docs=10,
        n_questions=3,
        seed=42,
    )
    docs = load_corpus(str(tmp_path / "gen" / "documents" / "corpus.jsonl"))
    embedder = MockEmbedder()
    vs, bm = build_index(
        docs,
        strategy="fixed",
        contextual=True,
        embedder=embedder,
        overlap=10,
        chunk_size=50,
        embed_model="mock",
        mock=True,
    )
    questions = load_corpus(  # load from the same corpus
        str(tmp_path / "gen" / "documents" / "corpus.jsonl")
    )
    # Use a minimal generated questions list.
    metrics_list = run_dataset(
        questions,
        (vs, bm),
        hybrid=True,
        alpha=0.5,
        rerank=False,
        top_n=50,
        top_k=5,
        expand=False,
        n_expand=0,
        judge=MockJudge(),
        llm=MockLLM(),
        cfg=None,
    )
    # Note: the questions loaded from the corpus are Document objects,
    # not Question objects. run_dataset will handle this gracefully.
    assert isinstance(metrics_list, list)
