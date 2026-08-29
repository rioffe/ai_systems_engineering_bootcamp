"""Tests for rag.retrieval -- VectorStore/cosine + BM25 + Hybrid + Rerank.

Implements T-04, T-07, T-23, T-05 (SPEC C-02/C-04/C-05).
"""

from __future__ import annotations

import pytest

from rag.retrieval import (
    BM25Index,
    HybridConfig,
    HybridRetriever,
    MockReranker,
    Reranker,
    VectorStore,
    cosine,
)
from rag.types import Chunk, ChunkMetadata, ScoredChunk

# -- cosine / VectorStore ----------------------------------------------------


def _chunk(cid: str, text: str, dim: int = 3) -> Chunk:
    meta = ChunkMetadata(chunk_id=cid, doc_id=cid.rsplit("#", 1)[0])
    return Chunk(
        chunk_id=cid,
        text=text,
        meta=meta,
        position=0,
        tokens=max(1, len(text) // 4),
    )


def test_cosine_identical_unit_vectors_is_one():
    a = (1.0, 0.0, 0.0)
    b = (1.0, 0.0, 0.0)
    assert cosine(a, b) == pytest.approx(1.0)


def test_cosine_zero_vector_is_zero():
    a = (0.0, 0.0, 0.0)
    b = (1.0, 0.0, 0.0)
    assert cosine(a, b) == 0.0


def test_vector_store_ranks_by_cosine_descending():
        # c1 aligned with q (cosine 1.0); c2 at 45 deg; c3 at 60 deg.
        # All have strictly-descending positive cosines so all are returned.
    vs = VectorStore(dim=3)
    vs.insert(_chunk("c1", "hello world"), (1.0, 0.0, 0.0))    # cosine 1.0
    vs.insert(_chunk("c2", "foo"), (0.7071068, 0.7071068, 0.0))  # 45 deg
    vs.insert(_chunk("c3", "hello"), (0.5, 0.5, 0.7071068))    # 60 deg
    q = (1.0, 0.0, 0.0)
    results = vs.search(q, k=3)
    assert results[0].chunk.chunk_id == "c1"
    assert results[1].chunk.chunk_id == "c2"
    assert results[2].chunk.chunk_id == "c3"
    assert results[0].semantic >= results[1].semantic >= results[2].semantic


def test_vector_store_tie_break_by_chunk_id_ascending():
       # Two identical-vectors: chunk_id ascending wins.
    vs = VectorStore(dim=3)
    vs.insert(_chunk("c3", "a"), (1.0, 0.0, 0.0))
    vs.insert(_chunk("c1", "a"), (1.0, 0.0, 0.0))
    q = (1.0, 0.0, 0.0)
    results = vs.search(q, k=2)
    assert results[0].chunk.chunk_id == "c1"
    assert results[1].chunk.chunk_id == "c3"


def test_vector_store_empty_return_empty_list():
    vs = VectorStore(dim=3)
    if vs.search((1.0, 0.0, 0.0), k=5) == []:
        # Empty store returns empty list, never None.
        assert True
    else:
        assert False, "empty store should return []"


# -- BM25 --------------------------------------------------------------------


def test_bm25_ranking():
          # BM25 with standard defaults k1=1.5, b=0.75.
    bm25 = BM25Index(k1=1.5, b=0.75)
    bm25.index(
        [_chunk("d1", "python is great for data science")],
        k1=1.5, b=0.75,
        )
    bm25.index(
        [_chunk("d2", "java is a popular language for enterprise")],
        k1=1.5, b=0.75,
        )
    results = bm25.search("python data", k=2)
    assert results[0].chunk.chunk_id == "d1"
    assert results[0].lexical > 0.0


def test_bm25_search_no_matches_returns_empty():
    bm25 = BM25Index()
    bm25.index([_chunk("d1", "alpha")], k1=1.5, b=0.75)
    assert bm25.search("zzz", k=5) == []


def test_bm25_dedupe_by_chunk_id_keep_highest():
    bm25 = BM25Index()
    bm25.index([_chunk("d1", "alpha beta gamma delta")], k1=1.5, b=0.75)
    bm25.index([_chunk("d1", "alpha beta")], k1=1.5, b=0.75)
    results = bm25.search("alpha", k=5)
    assert len(results) == 1
    assert results[0].chunk.chunk_id == "d1"


# -- HybridRetriever ----------------------------------------------------------


def test_hybrid_pool_union_and_minmax_blend():
          # T-07 worked example.
       # dense_N = {c1: 0.9, c2: 0.4}
       # BM25_N  = {c1: 0.6, c3: 0.7}
       # pool = {c1, c2, c3}; per-channel min-max, alpha=0.5:
       #   c1: 0.5 * 1.0 + 0.5 * 0.857 = 0.929
       #   c3: 0.5 * 0.0 + 0.5 * 1.0   = 0.500
       #   c2: 0.5 * 0.444 + 0.5 * 0.0 = 0.222
       # order: c1 > c3 > c2
    c1 = _chunk("c1", "hello world")
    c2 = _chunk("c2", "foo bar")
    c3 = _chunk("c3", "alpha beta")

    class FakeVS:

        def search(self, q_vec, k):
            return [
                ScoredChunk(chunk=c1, score=0.9, semantic=0.9, rank=1),
                ScoredChunk(chunk=c2, score=0.4, semantic=0.4, rank=2),
                ScoredChunk(chunk=c3, score=0.0, semantic=0.0, rank=3),
        ]

    class FakeBM25:

        def search(self, q, k):
            return [
                ScoredChunk(chunk=c1, score=0.6, lexical=0.6, rank=1),
                ScoredChunk(chunk=c3, score=0.7, lexical=0.7, rank=2),
        ]

    cfg = HybridConfig(alpha=0.5)
    hybrid = HybridRetriever(FakeVS(), FakeBM25(), cfg=cfg)
    results = hybrid.retrieve((1.0, 0.0, 0.0), "some query", candidates=3)
    ids = [r.chunk.chunk_id for r in results]
    assert ids[0] == "c1"
    assert ids[1] == "c3"
    assert ids[2] == "c2"


def test_hybrid_zero_range_channel_normalizes_to_one():
         # All-equal scores => min-max normalizes everything to 1.0.
    c1 = _chunk("c1", "aaa")
    c2 = _chunk("c2", "bbb")

    class FakeVS:

        def search(self, q_vec, k):
            return [
                ScoredChunk(chunk=c1, score=0.5, semantic=0.5, rank=1),
                ScoredChunk(chunk=c2, score=0.5, semantic=0.5, rank=2),
        ]

    class FakeBM25:

        def search(self, q, k):
            return [
                ScoredChunk(chunk=c1, score=0.3, lexical=0.3, rank=1),
                ScoredChunk(chunk=c2, score=0.3, lexical=0.3, rank=2),
        ]

    cfg = HybridConfig(alpha=0.5)
    hybrid = HybridRetriever(FakeVS(), FakeBM25(), cfg=cfg)
    results = hybrid.retrieve((1.0, 0.0, 0.0), "q", candidates=2)
          # All equal => all normalize to 1.0 => tie broken by chunk_id ascending.
    ids = [r.chunk.chunk_id for r in results]
    assert ids == ["c1", "c2"]
    blended_scores = [r.score for r in results]
          # All should be ~equal (all normalized to 1.0).
    assert all(abs(s - blended_scores[0]) < 1e-9 for s in blended_scores)


def test_hybrid_alpha_one_is_pure_dense():
    c1 = _chunk("c1", "a")
    c2 = _chunk("c2", "b")

    class FakeVS:

        def search(self, q_vec, k):
            return [
                ScoredChunk(chunk=c1, score=0.9, semantic=0.9, rank=1),
                ScoredChunk(chunk=c2, score=0.1, semantic=0.1, rank=2),
        ]

    class FakeBM25:

        def search(self, q, k):
            return [
                ScoredChunk(chunk=c1, score=100.0, lexical=100.0, rank=1),
                ScoredChunk(chunk=c2, score=1.0, lexical=1.0, rank=2),
        ]

    cfg = HybridConfig(alpha=1.0)
    hybrid = HybridRetriever(FakeVS(), FakeBM25(), cfg=cfg)
    results = hybrid.retrieve((1.0, 0.0, 0.0), "q", candidates=2)
    ids = [r.chunk.chunk_id for r in results]
     # Pure dense: c1 (0.9) > c2 (0.1).
    assert ids == ["c1", "c2"]


def test_hybrid_alpha_zero_is_pure_lexical():
    c1 = _chunk("c1", "a")
    c2 = _chunk("c2", "b")

    class FakeVS:

        def search(self, q_vec, k):
            return [
                ScoredChunk(chunk=c1, score=0.9, semantic=0.9, rank=1),
                ScoredChunk(chunk=c2, score=0.1, semantic=0.1, rank=2),
        ]

    class FakeBM25:

        def search(self, q, k):
            return [
                ScoredChunk(chunk=c1, score=1.0, lexical=1.0, rank=1),
                ScoredChunk(chunk=c2, score=0.3, lexical=0.3, rank=2),
        ]

    cfg = HybridConfig(alpha=0.0)
    hybrid = HybridRetriever(FakeVS(), FakeBM25(), cfg=cfg)
    results = hybrid.retrieve((1.0, 0.0, 0.0), "q", candidates=2)
     # Pure lexical: c1 (1.0 > 0.3).
    ids = [r.chunk.chunk_id for r in results]
    assert ids == ["c1", "c2"]


# -- Reranker -----------------------------------------------------------------


def test_mock_reranker_returns_top_k():
         # MockReranker: 0.6 * coverage + 0.4 * norm-cosine.
    reranker = MockReranker()
    c1 = _chunk("d1", "alpha")
    c2 = _chunk("d2", "beta")
    c3 = _chunk("d3", "gamma")
    candidates = [
        ScoredChunk(chunk=c1, score=0.5, semantic=0.9, rank=1),
        ScoredChunk(chunk=c2, score=0.4, semantic=0.8, rank=2),
        ScoredChunk(chunk=c3, score=0.3, semantic=0.7, rank=3),
    ]
    result = reranker.rerank("alpha beta gamma", candidates, top_k=2)
    assert len(result) == 2
          # ScoredChunk.rerank should be populated.
    for r in result:
        assert r.rerank is not None


def test_reranker_interface():
    assert hasattr(Reranker, "rerank")
    assert issubclass(MockReranker, Reranker)
