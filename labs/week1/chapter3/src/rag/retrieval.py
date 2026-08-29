"""Retrieval: VectorStore / cosine / BM25 / HybridRetriever / Reranker.

Implements C-02 / C-04 / C-05 from SPEC.md.
"""

from __future__ import annotations

import math
from typing import Protocol, runtime_checkable

from rag.embedding import tokenizer
from rag.types import Chunk, ScoredChunk


@runtime_checkable
class DenseChannel(Protocol):
    def search(self, q_vec: tuple[float, ...], k: int) -> list[ScoredChunk]: ...


@runtime_checkable
class LexicalChannel(Protocol):
    def search(self, query: str, k: int) -> list[ScoredChunk]: ...


def cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class VectorStore:
    def __init__(self, dim: int) -> None:
        self.dim = dim
        self._entries: list[tuple[ScoredChunk, tuple[float, ...]]] = []
        self._data: dict[str, tuple[Chunk, tuple[float, ...]]] = {}

    def insert(self, chunk: Chunk, vector: tuple[float, ...]) -> None:
        sc = ScoredChunk(chunk=chunk, score=0.0, semantic=0.0, rank=0)
        self._entries.append((sc, vector))
        self._data[chunk.chunk_id] = (chunk, vector)

    def search(self, q_vec: tuple[float, ...], k: int) -> list[ScoredChunk]:
        results: list[ScoredChunk] = []
        for sc, vec in self._entries:
            c = cosine(q_vec, vec)
            if c > 0.0:
                sc.score = c
                sc.semantic = c
                results.append(sc)
        results.sort(key=lambda sc: (-sc.semantic, sc.chunk.chunk_id))
        out = results[:k]
        for i, sc in enumerate(out, start=1):
            sc.rank = i
        return out


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75, *, dim: int = 256) -> None:
        self.k1 = k1
        self.b = b
        self._docs: list[Chunk] = []
        self._tf: list[dict[str, int]] = []
        self._df: dict[str, int] = {}
        self._dl: list[int] = []
        self._data: dict[str, Chunk] = {}

    def index(self, chunks: list[Chunk], k1: float | None = None, b: float | None = None) -> None:
        # O-3a dedup by chunk_id: skip a chunk_id already indexed (keep first).
        known = {d.chunk_id for d in self._docs}
        for chunk in chunks:
            if chunk.chunk_id in known:
                continue
            known.add(chunk.chunk_id)
            toks = tokenizer(chunk.text)
            tf: dict[str, int] = {}
            for t in toks:
                tf[t] = tf.get(t, 0) + 1
            for t in tf:
                self._df[t] = self._df.get(t, 0) + 1
            self._docs.append(chunk)
            self._tf.append(tf)
            self._dl.append(len(toks))

    def search(self, query: str, k: int) -> list[ScoredChunk]:
        q_toks = tokenizer(query)
        n = len(self._docs)
        if n == 0:
            return []
        avgdl = sum(self._dl) / n
        scored: list[tuple[Chunk, float]] = []
        for i in range(n):
            tf = self._tf[i]
            dl = self._dl[i]
            s = 0.0
            for t in q_toks:
                if t not in tf:
                    continue
                f = tf[t]
                idf = math.log(1.0 + (n - self._df[t] + 0.5) / (self._df[t] + 0.5))
                denom = f + self.k1 * (1.0 - self.b + self.b * dl / avgdl)
                s += idf * f * (self.k1 + 1.0) / denom
            if s > 0.0:
                scored.append((self._docs[i], s))
        scored.sort(key=lambda x: (-x[1], x[0].chunk_id))
        out: list[ScoredChunk] = []
        for i, (doc, s) in enumerate(scored[:k], start=1):
            out.append(ScoredChunk(chunk=doc, score=0.0, lexical=s, rank=i))
        return out


from dataclasses import dataclass


@dataclass
class HybridConfig:
    alpha: float = 0.5
    s_sem_norm: str = "minmax"
    s_lex_norm: str = "minmax"
    combine: str = "linear"


class HybridRetriever:
    def __init__(
        self,
        store: DenseChannel,
        bm25: LexicalChannel,
        *,
        cfg: HybridConfig | None = None,
        candidates: int = 20,
    ) -> None:
        self.store = store
        self.bm25 = bm25
        self.cfg = cfg or HybridConfig()
        self.candidates = candidates

    @staticmethod
    def _minmax_norm(values: dict[str, float]) -> dict[str, float]:
        vals = list(values.values())
        if not vals:
            return {}
        lo = min(vals)
        hi = max(vals)
        if hi == lo:
            return {key: 1.0 for key in values}
        return {key: (val - lo) / (hi - lo) for key, val in values.items()}

    def retrieve(
        self, q_vec: tuple[float, ...], query: str, *, candidates: int | None = None
    ) -> list[ScoredChunk]:
        n = candidates or self.candidates
        dense = self.store.search(q_vec, n)
        lexical = self.bm25.search(query, n)
        sem_map: dict[str, float] = {}
        lex_map: dict[str, float] = {}
        chunk_by_id: dict[str, Chunk] = {}
        for sc in dense:
            cid = sc.chunk.chunk_id
            sem_map[cid] = sc.semantic
            chunk_by_id[cid] = sc.chunk
        for sc in lexical:
            cid = sc.chunk.chunk_id
            lex_map[cid] = sc.lexical
            chunk_by_id.setdefault(cid, sc.chunk)
        pool = set(sem_map) | set(lex_map)
        for cid in pool:
            sem_map.setdefault(cid, 0.0)
            lex_map.setdefault(cid, 0.0)
        sem_norm = self._minmax_norm(sem_map)
        lex_norm = self._minmax_norm(lex_map)
        alpha = self.cfg.alpha
        scores: list[ScoredChunk] = []
        for cid in pool:
            blend = alpha * sem_norm.get(cid, 0.0) + (1.0 - alpha) * lex_norm.get(cid, 0.0)
            scores.append(
                ScoredChunk(
                    chunk=chunk_by_id[cid],
                    score=blend,
                    semantic=sem_norm.get(cid, 0.0),
                    lexical=lex_norm.get(cid, 0.0),
                    rank=0,
                )
            )
        scores.sort(key=lambda sc: (-sc.score, sc.chunk.chunk_id))
        for i, sc in enumerate(scores, start=1):
            sc.rank = i
        return scores


from abc import ABC, abstractmethod


class Reranker(ABC):
    @abstractmethod
    def rerank(self, query: str, candidates: list[ScoredChunk], *, top_k: int) -> list[ScoredChunk]:
        raise NotImplementedError


class MockReranker(Reranker):
    COVERAGE_WEIGHT = 0.6
    COS_WEIGHT = 0.4

    def rerank(self, query: str, candidates: list[ScoredChunk], *, top_k: int) -> list[ScoredChunk]:
        q_tokens = set(tokenizer(query))
        if not q_tokens:
            return candidates[:top_k]
        max_sem = max((sc.semantic for sc in candidates), default=0.0) or 1.0
        for sc in candidates:
            chunk_tokens = tokenizer(sc.chunk.text)
            hit = q_tokens.intersection(chunk_tokens)
            coverage = len(hit) / len(q_tokens)
            norm_cos = sc.semantic / max_sem
            sc.rerank = round(self.COVERAGE_WEIGHT * coverage + self.COS_WEIGHT * norm_cos, 10)
        scored = sorted(candidates, key=lambda sc: (-(sc.rerank or 0.0), sc.chunk.chunk_id))
        for i, sc in enumerate(scored[:top_k], start=1):
            sc.rank = i
        return scored[:top_k]

