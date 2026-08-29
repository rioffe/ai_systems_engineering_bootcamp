"""Citation: grounding gate + claim extraction + injection scan.

Implements C-08 / R-08 / R-21 / I-003 / E-16 / T-08c from SPEC.md.
"""
from __future__ import annotations

import re

from rag.types import Answer, Chunk, Citation, ScoredChunk

# -- Claim extraction pattern ------------------------------------------------

_CLAIM_SPLIT_RE = re.compile(r"[.;!]")

# -- Injection-detection patterns --------------------------------------------
# Keywords that indicate a prompt-injection payload embedded in retrieved
# evidence.  A hit sets injection_warning=True and records the offending
# chunk_id(s).  Per R-21 the payload is DATA, not an instruction.
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
        re.compile(r"ignore all previous instructions", re.IGNORECASE),
        re.compile(r"ignore previous instructions", re.IGNORECASE),
        re.compile(r"disregard(?: all )?previous", re.IGNORECASE),
        re.compile(r"reveal your (?:system|inner)", re.IGNORECASE),
        re.compile(r"\bsystem prompt", re.IGNORECASE),
        re.compile(r"print your own instructions", re.IGNORECASE),
        re.compile(r"you are now", re.IGNORECASE),
        re.compile(r"override the system", re.IGNORECASE),
        re.compile(r"disregard the (?:rules|instructions)", re.IGNORECASE),
]


class InjectionResult:
    injection_warning: bool = False
    offending_chunk_ids: list[str]

    def __init__(self,
                warning: bool,
                offending: list[str] | None = None) -> None:
        self.injection_warning = warning
        self.offending_chunk_ids = offending or []


class CitationResult:
    grounding_violation: bool = False
    dropped_chunk_ids: list[str]
    citations: list[Citation]

    def __init__(self,
                citations: list[Citation],
                dropped_chunk_ids: list[str] | None = None,
                grounding_violation: bool = False) -> None:
        self.citations = citations
        self.dropped_chunk_ids = dropped_chunk_ids or []
        self.grounding_violation = grounding_violation


class Citer:
    def extract_claims(self, text: str) -> list[str]:
        if not text:
            return []
        parts = _CLAIM_SPLIT_RE.split(text)
        return [p.strip() for p in parts if p.strip()]

    def citations_from_answer(self, answer: Answer) -> list[Citation]:
           # Parse [c:claim,chunk:doc#i,section:?] markers in text.
        pattern = re.compile(
            r"\[c:([^,]+),chunk:([^\]]+?)"
            r"(?:,section:([^\]]+?))?\]")
        result: list[Citation] = []
        seen_cids: set[str] = set()
        for mtch in pattern.finditer(answer.text):
            label = mtch.group(1).strip()
            chunk_id = mtch.group(2).strip()
            section = mtch.group(3).strip() if mtch.group(3) else None
            if chunk_id in seen_cids:
                continue
            seen_cids.add(chunk_id)
            for cit in answer.citations:
                if cit.chunk_id == chunk_id:
                    cit.section = section or cit.section
                    result.append(cit)
                    break
            else:
                result.append(Citation(
                    claim=label,
                    source=chunk_id.rsplit("#", 1)[0],
                    chunk_id=chunk_id,
                    section=section,
                ))
        return result

    def grounding_gate(
        self,
        answer: Answer,
        provenance: set[str],
        ) -> CitationResult:
        parsed = self.citations_from_answer(answer)
        kept: list[Citation] = []
        dropped: list[str] = []
        for c in parsed:
            if c.chunk_id in provenance:
                kept.append(c)
            else:
                dropped.append(c.chunk_id)
        return CitationResult(
            citations=kept,
            dropped_chunk_ids=dropped,
            grounding_violation=len(dropped) > 0,
        )

    def scan_injection(
        self,
        chunks: list[ScoredChunk],
        ) -> InjectionResult:
        offending: list[str] = []
        for sc in chunks:
            ch = sc.chunk
            text = ch.embed_text or ch.text
            for pat in _INJECTION_PATTERNS:
                if pat.search(text) and ch.chunk_id not in offending:
                    offending.append(ch.chunk_id)
                    break
        return InjectionResult(
            len(offending) > 0,
            offending=offending,
        )
