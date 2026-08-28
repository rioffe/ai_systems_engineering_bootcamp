"""Chunking strategies + boundary guard.

Implements C-03 / R-03 / I-013 from SPEC.md.
"""

from __future__ import annotations

import re

from loguru import logger

from rag.types import Chunk, ChunkMetadata, Document


class Chunker:
         # Abstract base for all chunking strategies.
     def chunk(self, doc: Document, *,
               overlap: int = 0) -> list[Chunk]:
         raise NotImplementedError

     def __init_subclass__(cls) -> None:
          pass


def _build_meta(doc: Document, index: int, chunk_id: str) -> ChunkMetadata:
        # Propagate document metadata into a chunk.
    return ChunkMetadata(
        chunk_id=chunk_id,
        doc_id=doc.doc_id,
        title=doc.metadata.title,
        section=doc.metadata.section,
        domain=doc.metadata.domain,
        author=doc.metadata.author,
        created_at=doc.metadata.created_at,
        updated_at=doc.metadata.updated_at,
        version=doc.metadata.version,
        access_level=doc.metadata.access_level,
    )


class FixedChunker(Chunker):
        # Naive fixed-size + overlap character chunks.
    def __init__(self, *,
                  strategy: str = "fixed",
                  chunk_size: int = 800,
                  overlap: int = 200) -> None:
        self.strategy = strategy
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, doc: Document, *,
              overlap: int | None = None) -> list[Chunk]:
        ov = overlap if overlap is not None else self.overlap
        text = doc.text
        step = max(1, self.chunk_size - ov)
        out: list[Chunk] = []
        pos = 0
        i = 0
        while pos < len(text):
            end = min(pos + self.chunk_size, len(text))
            seg = text[pos:end]
            chunk_id = f"{doc.doc_id}#{i}"
            out.append(Chunk(
                chunk_id=chunk_id,
                text=seg,
                meta=_build_meta(doc, i, chunk_id),
                position=i,
                embed_text=seg,
            ))
            if end >= len(text):
                break
            pos += step
            i += 1
        return out


def _split_by_headings(text: str) -> list[str]:
        # Split on markdown-style heading markers (# / ## / Article / Section).
    lines = text.split("\n")
    sections: list[list[str]] = []
    current: list[str] = []
    heading_re = re.compile(
        r"^(#{1,6}\s.*)|^(Article\s+\d+)|^(Section\s+\d+)")
    for line in lines:
        if heading_re.match(line):
            if current:
                sections.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append(current)
    out: list[str] = []
    for sec in sections:
        joined = "\n".join(sec).strip()
        if joined:
            out.append(joined)
    return out


class HeadingChunker(Chunker):
        # Split on heading markers; never across a heading boundary.
    def __init__(self, *,
                  strategy: str = "heading",
                  chunk_size: int = 800,
                  overlap: int = 200) -> None:
        self.strategy = strategy
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, doc: Document, *,
              overlap: int | None = None) -> list[Chunk]:
        sections = _split_by_headings(doc.text)
        out: list[Chunk] = []
        for i, sec_text in enumerate(sections):
            chunk_id = f"{doc.doc_id}#{i}"
            parts = sec_text.split("\n", 1)
            title = parts[0]
            section = parts[1].strip() if len(parts) > 1 else sec_text
            meta = _build_meta(doc, i, chunk_id)
            meta.title = title
            meta.section = section
            out.append(Chunk(
                chunk_id=chunk_id,
                text=sec_text,
                meta=meta,
                position=i,
                embed_text=sec_text,
             ))
        return out


class ContextualChunker(Chunker):
        # Wrap another chunker and add the contextual embedding prefix.
    def __init__(self, *,
                  overlay: Chunker | None = None,
                  strategy: str = "contextual",
                  chunk_size: int = 800,
                  overlap: int = 200) -> None:
        if overlay is None:
            overlay = FixedChunker(
                strategy="fixed",
                chunk_size=chunk_size,
                overlap=overlap,
            )
        self.overlay = overlay
        self.strategy = strategy
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, doc: Document, *,
              overlap: int | None = None) -> list[Chunk]:
        title = doc.metadata.title or doc.doc_id
        section = doc.metadata.section or ""
        prefix = f"Document: {title}\nSection: {section}\n\n"
        out: list[Chunk] = []
        for c in self.overlay.chunk(doc):
            out.append(Chunk(
                chunk_id=c.chunk_id,
                text=c.text,
                context=prefix,
                embed_text=prefix + c.text,
                meta=c.meta,
                position=c.position,
                tokens=c.tokens,
                split_risk=c.split_risk,
            ))
        return out


def _find_sentence_end(text: str, start: int,
                       window: int) -> int | None:
        # Find the last sentence boundary in [start, start+window].
    end_pos = min(start + window, len(text))
        # Search backwards from end_pos for a sentence boundary char.
    for pos in range(end_pos - 1, start - 1, -1):
        after_ok = pos + 1 >= len(text) or text[pos + 1] == " "
        if text[pos] in ".!?" and after_ok:
            return pos + 2
    return None


def boundary_guard(chunks: list[Chunk],
                   overlap: int = 200) -> list[Chunk]:
        # I-013: pull a naive mid-sentence cut up to the last sentence
        # end within the overlap window; if none, keep the larger unit
        # and flag split_risk.
    n = len(chunks)
    for i in range(max(0, n - 1)):
        chunk = chunks[i]
        ends_clean = chunk.text.rstrip().endswith((".", "?", "!"))
        if ends_clean:
            continue
        full = chunks[i].text + chunks[i + 1].text
        sent_end = _find_sentence_end(full, 0, overlap)
        if sent_end is not None and 0 < sent_end < len(full):
            new_text = full[:sent_end]
            rest = full[sent_end:]
            chunks[i] = Chunk(
                chunk_id=chunks[i].chunk_id,
                text=new_text,
                context=chunks[i].context,
                embed_text=new_text,
                meta=chunks[i].meta,
                position=chunks[i].position,
                tokens=chunks[i].tokens,
                split_risk=True,
            )
            if rest:
                chunks[i + 1] = Chunk(
                    chunk_id=chunks[i + 1].chunk_id,
                    text=rest,
                    context=chunks[i + 1].context,
                    embed_text=rest,
                    meta=chunks[i + 1].meta,
                    position=chunks[i + 1].position,
                    tokens=chunks[i + 1].tokens,
                    split_risk=chunks[i + 1].split_risk,
                )
        else:
            chunks[i] = Chunk(
                chunk_id=chunks[i].chunk_id,
                text=chunks[i].text,
                context=chunks[i].context,
                embed_text=chunks[i].embed_text,
                meta=chunks[i].meta,
                position=chunks[i].position,
                tokens=chunks[i].tokens,
                split_risk=True,
            )
        logger.debug(
            "boundary_guard: chunk_id={} split_risk=True (window={})",
            chunks[i].chunk_id, overlap,
        )
    return chunks
