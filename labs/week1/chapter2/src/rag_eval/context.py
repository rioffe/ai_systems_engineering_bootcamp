"""C-03 context construction -- the token-budget builder (R-03, §14/§3).

Turns the ranked ``ScoredDoc`` list into the single ``Context`` the LLM actually sees:
deduplicate, keep the ranked order, and fill toward the token budget by dropping the
lowest-score docs first, cutting the last doc's text to fit when even it would overflow
(E-05). Every included doc is labelled ``[doc_id]`` in the prompt so the answer can cite
its provenance (R-04 / I-003).

This module is part of the **deterministic boundary**: stdlib + ``types`` only, no LLM or
network (I-009 / T-02). The token estimator ``est_tokens`` (O-2) is the single formula
shared by the builder and any report (I-005): the reported ``Context.tokens`` is exactly
what was built (I-006).
"""

from __future__ import annotations

from .types import Context, ScoredDoc

# O-2 token estimate. Approximate by design (a real tokenizer would leak a model into the
# deterministic boundary, contradicting I-009 -- Q-04): ceil(chars / 4) ~ 4 chars/token.
# Empty text -> 0.
def est_tokens(text: str) -> int:
    n = len(text)
    return (n + 3) // 4 if n else 0


def _normalize(text: str) -> str:
    """Whitespace-normalized text used for the E-06 dedupe key."""
    return " ".join((text or "").split())


def build_context(
    scored: list[ScoredDoc],
    token_budget: int = 2000,
    dedupe: bool = True,
) -> Context:
    """Assemble the token-bounded ``Context`` from a ranked ``ScoredDoc`` list (C-03).

    Order of operations: dedupe identical texts (keep the highest rank), then fill the
    highest-score docs first, cutting the last doc's text to fit when it would overflow
    (E-05). ``truncated`` is True iff any doc was deduped out, dropped, or cut
    (E-05/E-06/I-004). ``Context.tokens == est_tokens(prompt) <= token_budget`` always
    (I-004/I-006).
    """
    if token_budget < 0:
        raise ValueError("token_budget must be >= 0")

    items = list(scored)
    # Canonical order: score desc, then doc_id asc (E-06 tie-break). This makes "first
    # occurrence" == "highest rank" regardless of the caller's input ordering.
    items.sort(key=lambda sd: (-sd.score, str(sd.doc.doc_id)))
    dedupe_dropped = 0
    if dedupe:
        seen: set[str] = set()
        kept: list[ScoredDoc] = []
        for sd in items:
            key = _normalize(sd.doc.text)
            if key in seen:
                dedupe_dropped += 1
                continue
            seen.add(key)
            kept.append(sd)
        items = kept

    included: list[ScoredDoc] = []
    assembled = ""
    partial = False
    for sd in items:
        full_block = f"[{sd.doc.doc_id}]\n{sd.doc.text}\n\n"
        candidate = assembled + full_block
        if est_tokens(candidate) <= token_budget:
            assembled = candidate
            included.append(sd)
            continue
        remaining_chars = token_budget * 4 - len(assembled)
        if remaining_chars <= 0:
            break
        sliver = full_block[:remaining_chars]
        if sliver.strip() == "":
            break
        sd = ScoredDoc(doc=sd.doc, score=sd.score, rank=sd.rank, truncated=True)
        assembled += sliver
        included.append(sd)
        partial = True
        break

    tokens = est_tokens(assembled)
    truncated = partial or dedupe_dropped > 0 or (len(included) < len(items))
    provenance = [sd.doc.doc_id for sd in included]
    return Context(
        docs=included,
        prompt=assembled,
        provenance=provenance,
        tokens=tokens,
        truncated=truncated,
    )


__all__ = ["Context", "build_context", "est_tokens"]
