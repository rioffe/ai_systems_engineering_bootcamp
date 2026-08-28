"""Tests for rag.context -- est_tokens + ContextBuilder.

Implements T-06, T-06a, T-06b (SPEC section 9.5, I-004 / I-005 / I-006).
"""

from __future__ import annotations

from rag.context import build_context, est_tokens
from rag.types import Chunk, ChunkMetadata, ScoredChunk


def _sc(chunk_id: str, text: str, rank: int) -> ScoredChunk:
    # Build a ScoredChunk with meta + position for tests.
    meta = ChunkMetadata(chunk_id=chunk_id, doc_id=chunk_id.rsplit("#", 1)[0])
    chunk = Chunk(
        chunk_id=chunk_id,
        text=text,
        meta=meta,
        position=rank - 1,
        tokens=est_tokens(text),
    )
    return ScoredChunk(chunk=chunk, score=float(rank), rank=rank)


def test_est_tokens_ceil_div_4():
    # O-2 / I-005: est_tokens(s) = ceil(len(s) / 4).
    assert est_tokens("") == 0  # ceil(0/4)
    assert est_tokens("abc") == 1  # ceil(3/4) = 1
    assert est_tokens("abcd") == 1  # ceil(4/4) = 1
    assert est_tokens("abcde") == 2  # ceil(5/4) = 2
    assert est_tokens("a" * 100) == 25  # 100/4 = 25 exactly
    assert est_tokens("a" * 101) == 26  # ceil(101/4) = 26


def test_build_context_running_sum_and_truncated():
    # T-06 / I-004 / I-006: Context.tokens = running sum over included docs;
    # truncated True iff a doc was dropped; context_tokens <= budget always.
    sc_a = _sc("a#0", "x" * 40, rank=1)  # 10 tokens
    sc_b = _sc("b#0", "y" * 40, rank=2)  # 10 tokens
    sc_c = _sc("c#0", "z" * 40, rank=3)  # 10 tokens
    # budget = 25 tokens: include a+b=20, drop c (next would be 30 > 25)
    ctx = build_context([sc_a, sc_b, sc_c], token_budget=25)
    assert ctx.tokens == 20  # running sum over included docs
    assert ctx.truncated
    assert set(ctx.provenance) == {"a#0", "b#0"}
    assert ctx.tokens <= 25
    # With enough budget, no truncation.
    ctx_full = build_context([sc_a, sc_b, sc_c], token_budget=100)
    assert ctx_full.tokens == 30
    assert not ctx_full.truncated
    assert set(ctx_full.provenance) == {"a#0", "b#0", "c#0"}


def test_build_context_empty_input_empty_provenance():
    # Empty retrieval -> empty Context, truncated=False, tokens=0.
    ctx = build_context([], token_budget=100)
    assert ctx.tokens == 0
    assert not ctx.truncated
    assert ctx.provenance == set()
    assert ctx.docs == []


def test_build_context_duplicate_content_drops_lower_rank():
    # T-06a / E-06 / I-004: identical text keeps highest-rank copy,
    # drops lower-rank duplicate without error; truncated=True.
    sc_dup1 = _sc("a#0", "hello world", rank=1)
    sc_dup2 = _sc("b#0", "hello world", rank=3)
    ctx = build_context([sc_dup1, sc_dup2], token_budget=100)
    # Only one copy of 'hello world' survives.
    assert len([d for d in ctx.docs if d.chunk.text == "hello world"]) == 1
    assert "a#0" in ctx.provenance
    assert "b#0" not in ctx.provenance
    # truncated flag must be set to signal the dedup event.
    assert ctx.truncated


def test_build_context_budget_smaller_than_each_doc():
    # E-05: budget smaller than every doc -> drop the overflowing doc.
    # Best-rank-first cannot rescue a doc that overflows by itself.
    sc_a = _sc("a#0", "x" * 40, rank=1)  # 10 tokens
    sc_b = _sc("b#0", "y" * 40, rank=2)  # 10 tokens
    ctx = build_context([sc_a, sc_b], token_budget=5)
    assert ctx.truncated
    assert ctx.docs == []
    assert ctx.tokens == 0
    assert ctx.provenance == set()


def test_build_context_provenance_matches_included_docs():
    # I-006 / T-06b: every id in provenance is a chunk in the included docs.
    sc_a = _sc("a#0", "alpha", rank=1)
    sc_b = _sc("b#0", "beta beta", rank=2)
    sc_c = _sc("c#0", "gamma gamma gamma", rank=3)
    ctx = build_context([sc_a, sc_b, sc_c], token_budget=30)
    # Provenance is exactly the chunk_ids present in ctx.docs.
    ids_in_docs = {d.chunk.chunk_id for d in ctx.docs}
    assert ctx.provenance == ids_in_docs


def test_build_context_single_doc_no_truncation():
    sc = _sc("a#0", "hello", rank=1)
    ctx = build_context([sc], token_budget=100)
    assert not ctx.truncated
    assert ctx.tokens == est_tokens("hello")
    assert ctx.provenance == {"a#0"}
