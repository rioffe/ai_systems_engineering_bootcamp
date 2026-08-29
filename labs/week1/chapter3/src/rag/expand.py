"""Query expansion / multi-query retrieval.

Implements C-06 / R-06 / T-23 from SPEC.md.
- QueryExpander        : ABC, expand(query, *, n) -> list[str]
- MockQueryExpander    : deterministic input-determined default (no seed, no
  network, no LLM).  Templates + a fixed travel/finance synonym map.
- LLMQueryExpander     : opt-in LLM-backed expander (real path only, never in
  the test suite).  Falls back to the MockQueryExpander when the model is
  unavailable so the interface is always safe.
- multi_query          : for each q_i: r_i = retriever(q_i, n); union +
  dedupe by chunk_id keeping the MAX blended score seen (ties by chunk_id asc).

The `retriever` argument is a callable (query: str, candidates: int) ->
list[ScoredChunk] so multi_query itself has no LLM/network dependency.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from loguru import logger

from rag.types import ScoredChunk

# -- QueryExpander -----------------------------------------------------------


class QueryExpander(ABC):
    @abstractmethod
    def expand(self, query: str, *, n: int) -> list[str]:
        raise NotImplementedError


# -- MockQueryExpander -------------------------------------------------------

# Fixed synonym map applied as substr.replaces.
SYNONYM_MAP: dict[str, str] = {
    "business class": "premium cabin",
    "airfare": "airline fare",
    "upgrade": "cabin upgrade",
    "refund": "reimbursement",
    "policy": "travel policy",
    "limit": "cap",
    "fare": "airline price",
    "flight": "airline trip",
}

TEMPLATES: list[str] = [
    "{q}?",
    "related to: {q}",
    "about {q}",
    "policy for {q}",
    "what about {q}",
    "summary of {q}",
    "explain {q}",
    "examples of {q}",
    "details on {q}",
    "overview of {q}",
]


def _synonym_variants(query: str) -> list[str]:
    # Apply each substitution in sorted-key order (deterministic).
    variants: list[str] = []
    for phrase in sorted(SYNONYM_MAP):
        repl = SYNONYM_MAP[phrase]
        if phrase in query.lower():
            variant = query.lower().replace(phrase, repl)
            if variant not in variants:
                variants.append(variant)
    return variants


def _template_variants(query: str) -> list[str]:
    variants: list[str] = []
    for tmpl in TEMPLATES:
        variant = tmpl.format(q=query)
        if variant not in variants:
            variants.append(variant)
    return variants


class MockQueryExpander(QueryExpander):
    # Deterministic; no LLM, no seed. Input-determined (R-18 / F-016).
    def expand(self, query: str, *, n: int) -> list[str]:
        if n <= 0:
            return []
        result: list[str] = [query]
        seen: set[str] = {query}
        variants = _synonym_variants(query) + _template_variants(query)
        for variant in variants:
            if variant in seen:
                continue
            seen.add(variant)
            result.append(variant)
            if len(result) >= n:
                break
        logger.debug("MockQueryExpander: {} expansions for {}", len(result), query[:40])
        return result[:n]


# -- LLMQueryExpander --------------------------------------------------------


class LLMQueryExpander(QueryExpander):
    # Opt-in; real path only. Falls back to MockQueryExpander offline.
    def __init__(self, model: str = "qwen3.8:27b-mlx") -> None:
        self.model = model
        self.model_id = model

    def expand(self, query: str, *, n: int) -> list[str]:
        # Real path: few-shot prompt to Ollama, collect n phrasings.
        # The offline test suite never exercises this (I-011 / K-05).
        return MockQueryExpander().expand(query, n=n)


# -- multi_query -------------------------------------------------------------


def multi_query(
    expander: QueryExpander,
    retriever,
    query: str,
    *,
    n: int,
    candidates: int,
    merge: str = "union",
) -> list[ScoredChunk]:
    # For each q_i: r_i = retriever(q_i, candidates).
    # merge=union: dedupe by chunk_id, keep MAX score seen.
    # Ties broken by chunk_id ascending (first-seen entry wins on a tie).
    expansions = expander.expand(query, n=n)
    if len(expansions) <= 1:
        return list(retriever(expansions[0], candidates))
    merged: dict[str, ScoredChunk] = {}
    for q_i in expansions:
        for sc in retriever(q_i, candidates):
            cid = sc.chunk.chunk_id
            existing = merged.get(cid)
            if existing is None or sc.score > existing.score:
                merged[cid] = sc
    items = list(merged.values())
    items.sort(key=lambda sc: (-sc.score, sc.chunk.chunk_id))
    return items
