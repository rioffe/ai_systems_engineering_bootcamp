"""Tests for rag.expand -- MockQueryExpander + multi_query.

Implements R-06 / C-06 / T-23, T-04b (SPEC section 8 / section 9).
"""

from __future__ import annotations

from rag.expand import (
    LLMQueryExpander,
    MockQueryExpander,
    QueryExpander,
    multi_query,
)

from rag.types import Chunk, ChunkMetadata, ScoredChunk


def _chunk(cid: str, text: str) -> Chunk:
    meta = ChunkMetadata(chunk_id=cid, doc_id=cid.rsplit("#", 1)[0])
    return Chunk(chunk_id=cid, text=text, meta=meta, position=0, tokens=max(1, len(text) // 4))


def test_mock_expander_original_is_first():
    exp = MockQueryExpander()
    out = exp.expand("How do I get a business class upgrade", n=3)
    assert out[0] == "How do I get a business class upgrade"


def test_mock_expander_produces_n_expansions():
    exp = MockQueryExpander()
    out = exp.expand("business class airfare refund", n=4)
    assert len(out) == 4
    assert len(set(out)) == 4  # all distinct


def test_mock_expander_is_deterministic():
    exp = MockQueryExpander()
    out = exp.expand("business class airfare refund", n=5)
    out2 = exp.expand("business class airfare refund", n=5)
    assert out == out2


def test_mock_expander_applies_synonyms():
    exp = MockQueryExpander()
    out = exp.expand("business class airfare", n=4)
    joined = " ".join(out).lower()
    assert "premium cabin" in joined or "airfare" in joined


def test_mock_expander_n_one_collapses():
    exp = MockQueryExpander()
    out = exp.expand("some query", n=1)
    assert out == ["some query"]


def test_mock_expander_no_duplicate_expansions():
    exp = MockQueryExpander()
    out = exp.expand("business class airfare refund policy", n=6)
    assert len(out) == len(set(out))


def test_multiquery_dedupe_keeps_max_score():
    c1 = _chunk("c1", "alpha document about fares")
    c2 = _chunk("c2", "beta document about refunds")
    c3 = _chunk("c3", "gamma document about policies")

    responses = {
        "exp0": [
            ScoredChunk(chunk=c1, score=0.5, semantic=0.5, rank=1),
            ScoredChunk(chunk=c2, score=0.8, semantic=0.8, rank=2),
        ],
        "exp1": [
            ScoredChunk(chunk=c1, score=0.9, semantic=0.9, rank=1),
            ScoredChunk(chunk=c3, score=0.3, semantic=0.3, rank=2),
        ],
        "exp2": [
            ScoredChunk(chunk=c2, score=0.2, semantic=0.2, rank=1),
        ],
    }

    class FakeExpander:
        def expand(self, q, *, n):
            return [f"exp{i}" for i in range(n)]

    def fake_ret(q, _candidates):
        return responses.get(q, [])

    merged = multi_query(
        FakeExpander(), fake_ret, "business class airfare", n=3, candidates=5, merge="union"
    )
    ids = [sc.chunk.chunk_id for sc in merged]
    assert len(set(ids)) == 3
    sc_map = {sc.chunk.chunk_id: sc for sc in merged}
    assert sc_map["c1"].score == 0.9
    assert sc_map["c2"].score == 0.8
    assert sc_map["c3"].score == 0.3
    assert merged[0].chunk.chunk_id == "c1"


def test_multiquery_n_one_collapses():
    c1 = _chunk("c1", "alpha about fares")

    class FakeExpander:
        def expand(self, q, *, n):
            return [q]

    def fake_ret(_q, _candidates):
        return [ScoredChunk(chunk=c1, score=0.7, semantic=0.7, rank=1)]

    merged = multi_query(
        FakeExpander(), fake_ret, "business class airfare", n=1, candidates=5, merge="union"
    )
    assert len(merged) == 1
    assert merged[0].chunk.chunk_id == "c1"
    assert merged[0].score == 0.7


def test_multiquery_sorted_by_score_desc():
    c1 = _chunk("c1", "x about fares")
    c2 = _chunk("c2", "y about refunds")
    c3 = _chunk("c3", "z about policies")

    responses = {
        "e0": [ScoredChunk(chunk=c1, score=0.4, semantic=0.4, rank=1)],
        "e1": [ScoredChunk(chunk=c2, score=0.9, semantic=0.9, rank=1)],
        "e2": [ScoredChunk(chunk=c3, score=0.6, semantic=0.6, rank=1)],
    }

    class FakeExpander:
        def expand(self, q, *, n):
            return [f"e{i}" for i in range(n)]

    def fake_ret(q, _candidates):
        return responses.get(q, [])

    merged = multi_query(FakeExpander(), fake_ret, "q", n=3, candidates=5, merge="union")
    ids = [sc.chunk.chunk_id for sc in merged]
    assert ids == ["c2", "c3", "c1"]


def test_multiquery_tie_break_chunk_id_ascending():
    cB = _chunk("cB", "x")
    cC = _chunk("cC", "y")

    class FakeExpander:
        def expand(self, q, *, n):
            return ["e0", "e1"]

    responses = {
        "e0": [ScoredChunk(chunk=cB, score=0.5, semantic=0.5, rank=1)],
        "e1": [ScoredChunk(chunk=cC, score=0.5, semantic=0.5, rank=1)],
    }

    def fake_ret(q, _candidates):
        return responses.get(q, [])

    merged = multi_query(FakeExpander(), fake_ret, "q", n=2, candidates=5, merge="union")
    ids = [sc.chunk.chunk_id for sc in merged]
    assert ids == ["cB", "cC"]


def test_llmqueryexpander_interface():
    assert issubclass(LLMQueryExpander, QueryExpander)
    exp = LLMQueryExpander(model="mock")
    assert callable(exp.expand)
