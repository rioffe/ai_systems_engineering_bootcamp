"""Shared type definitions for the RAG pipeline.

Implements C-01 / C-09 / C-10 data structures from SPEC.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CaseState(Enum):
    IDLE = "IDLE"
    RETRIEVING = "RETRIEVING"
    EXPANDING = "EXPANDING"
    RERANKING = "RERANKING"
    CONTEXTING = "CONTEXTING"
    GENERATING = "GENERATING"
    JUDGING = "JUDGING"
    SCORED = "SCORED"
    PARTIAL = "PARTIAL"
    ERROR = "ERROR"


@dataclass
class ChunkMetadata:
    """Section 7 metadata -- part of every Chunk; document fields propagate to chunks."""

    chunk_id: str  # "doc_id#i" -- stable and unique in corpus
    doc_id: str
    title: str | None = None
    section: str | None = None  # e.g. "4.2 Business-Class Airfare"
    domain: str | None = None  # coarse category (travel / finance / ...)
    author: str | None = None
    created_at: str | None = None  # ISO date YYYY-MM-DD
    updated_at: str | None = None  # ISO date
    version: int | float | None = None  # authority for conflict / recency
    access_level: str = "employee"  # CARRIED, NOT CONSUMED in v0.1 (F-009)


@dataclass
class Document:
    """A document with section 7 metadata."""

    doc_id: str
    text: str
    metadata: ChunkMetadata


@dataclass
class Chunk:
    """The retrieval unit (section 5)."""

    chunk_id: str
    text: str  # the chunk's own text (shown to LLM, cited)
    context: str | None = None  # section 12 contextual prefix
    embed_text: str | None = None  # what Embedder sees (section 12)
    meta: ChunkMetadata | None = None
    tokens: int = 0
    position: int = 0
    split_risk: bool = False  # I-013: True if a cut nears a boundary

    def __post_init__(self) -> None:
        if self.embed_text is None:
            self.embed_text = self.text


@dataclass
class ScoredChunk:
    """A chunk with its pre-rerank combined ranking score."""

    chunk: Chunk
    score: float  # PRE-RERANK combined score (hybrid or winning channel)
    semantic: float = 0.0  # raw dense (cosine) component
    lexical: float = 0.0  # raw BM25 component
    rerank: float | None = None  # reranker output when --rerank on
    rank: int = 0  # 1-based position in final list


@dataclass
class Citation:
    """A claim -> source -> chunk citation (section 13)."""

    claim: str
    source: str  # doc_id
    chunk_id: str
    section: str | None = None


@dataclass
class Question:
    """A question with ground truth for evaluation."""

    q_id: str
    question: str
    gold_answer: str
    gold_facts: list[str]  # expected facts -> completeness denominator
    relevant_chunks: list[str]  # ground truth chunk ids (TP/recall universe)
    relevant_docs: list[str]  # coarser: doc_ids for report / citation check
    tier: str  # one of: easy, multi, chunking, distractor, conflict, recency, injection


@dataclass
class Usage:
    """Token usage from a model call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class Answer:
    """LLM-generatable structured cited answer."""

    q_id: str
    text: str
    confidence: float
    citations: list[Citation] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    status: str = "COMPLETED"  # "COMPLETED" | "ERROR"
    error: str | None = None  # recorded on failure


@dataclass
class Verdict:
    """Judge's structured verdict."""

    q_id: str
    correct: bool = False
    supported: bool = False
    complete: bool = False
    unsupported_claims: list[str] = field(default_factory=list)
    total_factual_claims: int = 0
    faithfulness: float = 0.0
    completeness: float = 0.0
    citation_quality: float = 0.0
    injection_warning: bool = False
    grounding_violation: bool = False
    which_field_decided: str | None = None  # "version" | "updated_at" | None
    rationale: str = ""
    status: str = "JUDGED"  # "JUDGED" | "ERROR" | "SKIPPED"


@dataclass
class RunMetrics:
    """Per-case metrics from a pipeline run."""

    q_id: str
    tier: str
    # Retrieval fields (populated iff RETRIEVING cleared)
    retrieved: list[str] = field(
        default_factory=list
    )  # post-rerank top-k consumed by ContextBuilder
    expected: list[str] = field(default_factory=list)  # == question.relevant_chunks
    precision: float | None = None
    recall: float | None = None
    mrr: float | None = None
    ap: float | None = None
    ndcg: float | None = None
    capability_flags: dict[str, bool] = field(default_factory=dict)
    context_tokens: int = 0
    truncated: bool = False
    # Generation + judge fields
    answer_status: str | None = None
    correct: bool | None = None
    supported: bool | None = None
    complete: bool | None = None
    faithfulness: float | None = None
    completeness: float | None = None
    citation_quality: float | None = None
    unsupported_claims: list[str] = field(default_factory=list)
    injection_warning: bool = False
    grounding_violation: bool = False
    which_field_decided: str | None = None
    # Diagnostics
    failure_stage: str | None = (
        None  # None | retrieval|expansion|reranking|context|generation|judging
    )
    retrieve_ms: float = 0.0
    rerank_ms: float = 0.0
    generate_ms: float = 0.0
    total_latency_ms: float = 0.0
    status: str = "SCORED"  # "SCORED" | "PARTIAL" | "ERROR"


@dataclass
class TierMetrics:
    """Sub-aggregate for a single tier."""

    tier: str
    n: int = 0
    precision_sum: float = 0.0
    precision_count: int = 0
    recall_sum: float = 0.0
    recall_count: int = 0
    mrr_sum: float = 0.0
    mrr_count: int = 0
    ap_sum: float = 0.0
    ap_count: int = 0
    ndcg_sum: float = 0.0
    ndcg_count: int = 0
    faithfulness_sum: float = 0.0
    faithfulness_count: int = 0
    completeness_sum: float = 0.0
    completeness_count: int = 0
    citation_quality_sum: float = 0.0
    citation_quality_count: int = 0
    failure_breakdown: dict[str, int] = field(default_factory=dict)
    injection_count: int = 0
    grounding_violation_count: int = 0

    def add(self, rm: RunMetrics) -> None:
        """Accumulate a RunMetrics row into this tier."""
        self.n += 1
        p = rm.precision
        if p is not None:
            self.precision_sum += p
            self.precision_count += 1
        r = rm.recall
        if r is not None:
            self.recall_sum += r
            self.recall_count += 1
        m = rm.mrr
        if m is not None:
            self.mrr_sum += m
            self.mrr_count += 1
        a = rm.ap
        if a is not None:
            self.ap_sum += a
            self.ap_count += 1
        n = rm.ndcg
        if n is not None:
            self.ndcg_sum += n
            self.ndcg_count += 1
        f = rm.faithfulness
        if f is not None:
            self.faithfulness_sum += f
            self.faithfulness_count += 1
        c = rm.completeness
        if c is not None:
            self.completeness_sum += c
            self.completeness_count += 1
        q = rm.citation_quality
        if q is not None:
            self.citation_quality_sum += q
            self.citation_quality_count += 1
        if rm.failure_stage is not None:
            self.failure_breakdown[rm.failure_stage] = (
                self.failure_breakdown.get(rm.failure_stage, 0) + 1
            )
        if rm.injection_warning:
            self.injection_count += 1
        if rm.grounding_violation:
            self.grounding_violation_count += 1

    def means(self) -> dict[str, float | None]:
        """Compute the means over non-None rows."""

        def _mean(s: float, c: int) -> float | None:
            return s / c if c > 0 else None

        return {
            "precision": _mean(self.precision_sum, self.precision_count),
            "recall": _mean(self.recall_sum, self.recall_count),
            "mrr": _mean(self.mrr_sum, self.mrr_count),
            "ap": _mean(self.ap_sum, self.ap_count),
            "ndcg": _mean(self.ndcg_sum, self.ndcg_count),
            "faithfulness": _mean(self.faithfulness_sum, self.faithfulness_count),
            "completeness": _mean(self.completeness_sum, self.completeness_count),
            "citation_quality": _mean(self.citation_quality_sum, self.citation_quality_count),
        }


@dataclass
class AggregateMetrics:
    """Global aggregate over all RunMetrics, with by_tier and by_capability breakdowns."""

    n: int = 0
    precision_sum: float = 0.0
    precision_count: int = 0
    recall_sum: float = 0.0
    recall_count: int = 0
    mrr_sum: float = 0.0
    mrr_count: int = 0
    ap_sum: float = 0.0
    ap_count: int = 0
    ndcg_sum: float = 0.0
    ndcg_count: int = 0
    faithfulness_sum: float = 0.0
    faithfulness_count: int = 0
    completeness_sum: float = 0.0
    completeness_count: int = 0
    citation_quality_sum: float = 0.0
    citation_quality_count: int = 0
    by_tier: dict[str, TierMetrics] = field(default_factory=dict)
    by_capability: dict[str, TierMetrics] = field(default_factory=dict)
    failure_breakdown: dict[str, int] = field(default_factory=dict)
    injection_count: int = 0
    grounding_violation_count: int = 0

    def add(self, rm: RunMetrics) -> None:
        """Accumulate a RunMetrics row."""
        self.n += 1
        p = rm.precision
        if p is not None:
            self.precision_sum += p
            self.precision_count += 1
        r = rm.recall
        if r is not None:
            self.recall_sum += r
            self.recall_count += 1
        m = rm.mrr
        if m is not None:
            self.mrr_sum += m
            self.mrr_count += 1
        a = rm.ap
        if a is not None:
            self.ap_sum += a
            self.ap_count += 1
        n = rm.ndcg
        if n is not None:
            self.ndcg_sum += n
            self.ndcg_count += 1
        f = rm.faithfulness
        if f is not None:
            self.faithfulness_sum += f
            self.faithfulness_count += 1
        c = rm.completeness
        if c is not None:
            self.completeness_sum += c
            self.completeness_count += 1
        q = rm.citation_quality
        if q is not None:
            self.citation_quality_sum += q
            self.citation_quality_count += 1
        # by_tier
        t = rm.tier
        if t not in self.by_tier:
            self.by_tier[t] = TierMetrics(tier=t)
        self.by_tier[t].add(rm)
        # by_capability
        for cap, on in rm.capability_flags.items():
            if on:
                key = f"+{cap}"
                if key not in self.by_capability:
                    self.by_capability[key] = TierMetrics(tier=key)
                self.by_capability[key].add(rm)
        # failure breakdown
        if rm.failure_stage is not None:
            self.failure_breakdown[rm.failure_stage] = (
                self.failure_breakdown.get(rm.failure_stage, 0) + 1
            )
        if rm.injection_warning:
            self.injection_count += 1
        if rm.grounding_violation:
            self.grounding_violation_count += 1

    def means(self) -> dict[str, float | None]:
        """Compute the means over non-None rows."""

        def _mean(s: float, c: int) -> float | None:
            return s / c if c > 0 else None

        return {
            "precision": _mean(self.precision_sum, self.precision_count),
            "recall": _mean(self.recall_sum, self.recall_count),
            "mrr": _mean(self.mrr_sum, self.mrr_count),
            "ap": _mean(self.ap_sum, self.ap_count),
            "ndcg": _mean(self.ndcg_sum, self.ndcg_count),
            "faithfulness": _mean(self.faithfulness_sum, self.faithfulness_count),
            "completeness": _mean(self.completeness_sum, self.completeness_count),
            "citation_quality": _mean(self.citation_quality_sum, self.citation_quality_count),
        }
