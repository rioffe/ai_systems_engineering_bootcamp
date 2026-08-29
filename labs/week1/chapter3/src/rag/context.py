"""ContextBuilder -- token-budget assemble + dedupe + provenance.

Implements C-07 / I-004 / I-005 / I-006 from SPEC.md:
- est_tokens(s) = ceil(len(s) / 4) -- single formula, one place, I-005.
- build_context: dedupe by content (E-06), drop docs that overflow the running
 token-budget (E-05), provenance = chunk_ids of the included docs (I-006).
- Context.tokens is a running sum over included docs, never ceil of
 a concatenation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil

from loguru import logger

from rag.types import ScoredChunk


def est_tokens(s: str) -> int:
    # O-2 / I-005: ceil(len(s) / 4). Used identically by builder + report.
    if not s:
        return 0
    return ceil(len(s) / 4)


@dataclass
class Context:
    # Assembled token-bounded, deduped, source-labeled evidence for the LLM.
    # docs:       included ScoredChunks in rank order.
    # tokens:     running sum of est_tokens over included docs (I-004).
    # truncated:  True iff a doc was dropped (budget overflow or dedupe).
    # provenance: chunk_ids in the included docs.
    docs: list[ScoredChunk] = field(default_factory=list)
    tokens: int = 0
    truncated: bool = False
    provenance: set[str] = field(default_factory=set)


def build_context(
    scored: list[ScoredChunk],
    token_budget: int,
    *,
    dedupe_by_content: bool = True,
) -> Context:
    # Assemble a token-bounded, deduped, source-labeled Context.
    # Dedupe: two docs with identical text keep the highest-rank copy
    # (input is ranked ascending) and drop lower-rank duplicates (E-06/I-004),
    # setting truncated. Budget: before appending, check the running sum; drop
    # the doc that overflows and every subsequent one (E-05). Provenance is the
    # set of chunk_ids in the included docs (I-006).
    ctx = Context()
    if dedupe_by_content:
        seen: set[str] = set()
        deduped: list[ScoredChunk] = []
        for sc in scored:
            key = sc.chunk.text
            if key in seen:
                # Lower-rank duplicate drops silently except via the flag.
                ctx.truncated = True
                logger.debug("build_context: drop duplicate chunk_id={}", sc.chunk.chunk_id)
                continue
            seen.add(key)
            deduped.append(sc)
        scored = deduped
        # Overflow check below may also set ctx.truncated.
    for sc in scored:
        t = est_tokens(sc.chunk.text)
        # Before appending, check the budget guard (I-004 / E-05).
        if ctx.tokens + t > token_budget:
            # Drop this doc and every subsequent one; mark truncated.
            ctx.truncated = True
            logger.debug("build_context: budget overflow at chunk_id={}", sc.chunk.chunk_id)
            break
        ctx.tokens += t
        ctx.docs.append(sc)
    ctx.provenance = {sc.chunk.chunk_id for sc in ctx.docs}
    return ctx
