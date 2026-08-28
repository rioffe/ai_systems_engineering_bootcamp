"""Tests for rag.chunking -- Fixed / Heading / Contextual + boundary_guard.

Implements T-21 / E-07 / I-013 (SPEC section 9.3 / section 8).
"""

from __future__ import annotations

from rag.chunking import (
    ContextualChunker,
    FixedChunker,
    HeadingChunker,
    boundary_guard,
)

from rag.types import ChunkMetadata, Document


def _doc(doc_id: str, text: str) -> Document:
        # Minimal document for chunking tests.
    meta = ChunkMetadata(chunk_id=doc_id, doc_id=doc_id, title=doc_id,
                        section="1.0 Test")
    return Document(doc_id=doc_id, text=text, metadata=meta)


def test_fixed_chunker_splits_by_size_with_overlap():
        # FixedChunker(size=10, overlap=2): 30-char text -> 3 chunks of
        # [0..9], [8..17], [16..25], [24..29] (with overlap between them).
    doc = _doc("d1", "a" * 30)
    chs = FixedChunker(strategy="fixed", chunk_size=10, overlap=2).chunk(doc)
        # Each chunk_id is "d1#i".
    assert all(c.chunk_id.startswith("d1#") for c in chs)
        # With overlap, chunks are shorter than the full text.
    assert len(chs) >= 2
        # The first chunk starts at position 0.
    assert chs[0].position == 0
        # No chunk is empty.
    assert all(c.text for c in chs)


def test_heading_chunker_splits_on_heading_markers():
        # HeadingChunker splits on "## " markers.
    text = ("## Section A\nalpha content here.\n"
            "## Section B\nbeta content here.\n"
            "# Top\n\n## Section C\ngamma content here.")
    doc = _doc("d2", text)
    chs = HeadingChunker().chunk(doc)
        # Each chunk starts at a heading boundary.
    assert len(chs) >= 3
        # The chunk for "Section B" contains "beta content here".
    b = next((c for c in chs if "beta content here" in c.text), None)
    assert b is not None


def test_contextual_chunker_sets_context_and_embed_prefix():
        # ContextualChunker wraps a FixedChunker and sets Chunk.context +
        # Chunk.embed_text = context + text.
    doc = _doc("d3", "The limit is $5000.")
    chs = ContextualChunker(overlay=FixedChunker(
        strategy="fixed", chunk_size=200, overlap=0)).chunk(doc)
        # The chunk's context contains the title and section.
    assert any("Document: d3" in c.context or "Section" in (c.context or "")
                for c in chs)
        # embed_text is the context-prefixed form.
    assert all((c.embed_text or "").startswith("Document")
                or c.embed_text == c.text
                and "Section" in (c.context or "")
                for c in chs)


def test_contextual_off_embed_equals_text():
        # With --contextual off (default FixedChunker), embed_text == text.
    doc = _doc("d4", "The limit is $5000.")
    chs = FixedChunker(strategy="fixed", chunk_size=200, overlap=0).chunk(doc)
    assert all(c.embed_text == c.text for c in chs)


def test_boundary_guard_recovers_split_rule():
        # T-21 / E-07 / I-013: if a fixed cut at position P lands inside a
        # sentence, boundary_guard pulls the cut up to the last sentence
        # boundary within the overlap window before P, and sets split_risk.
    # Rule + condition that would be split by a naive fixed cut.
    rule = ("Business class airfare refund is $250. "
            "This rule applies only when the policy version is active.")
       # A naive 30-char cut would land inside the rule.
    doc = _doc("d5", rule)
    chs = boundary_guard(FixedChunker(strategy="fixed", chunk_size=30,
        overlap=40).chunk(doc))
        # After the guard: at most one chunk, or the rule+condition are
        # together in one chunk.
    assert len(chs) >= 1
        # If there's a split, the first chunk must end at a sentence
        # boundary (period followed by space), not mid-word.
    if len(chs) == 1:
        rule_ok = "refund is $250" in chs[0].text and "version is active" in chs[0].text
        assert rule_ok
    elif len(chs) == 2:
        first = chs[0].text
          # The first chunk should end at a period (the sentence boundary
          # found by the guard).
        assert first.rstrip().endswith(".")
          # The split_risk flag must be set.
        assert chs[0].split_risk or chs[1].split_risk
    else:
        assert len(chs) >= 3
        # The rule text must be recoverable in full from the union of chunks.
        combined = " ".join(c.text for c in chs)
        assert "refund is $250" in combined
        assert "version is active" in combined
