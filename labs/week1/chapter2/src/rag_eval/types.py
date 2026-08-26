"""C-01 / C-04 / C-07 record types (SPEC §4) -- the shared, headless contract.

Pure data: no LLM, no LLM-adjacent import, no network, no I/O. Every module the rest of
the system agrees on reduces to these dataclasses, which is what makes the deterministic
boundary swappable (R-17 / I-009): ``retrieval.py``, ``context.py``, ``metrics.py`` and
``corpus.py`` may import nothing here beyond these records (the source-scan T-02 pins that).

``Answer`` and ``Verdict`` are the *records* produced by the two probabilistic roles; their
``q_id`` is set by the pipeline after the object is generated (the LLM/Judge signatures,
C-05/C-06, do not carry the question id), so they are plain (non-frozen) dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Document:
    """A corpus document (C-01). ``doc_id`` equals the ``NNN`` filename stem when loaded
    from ``documents/`` and must match the id a question's ``relevant_docs`` names
    (I-013 / E-15). ``domain`` is a coarse category used for distractor grouping and
    provenance labels."""

    doc_id: str
    text: str
    domain: str | None = None

    def __post_init__(self) -> None:
        if not self.doc_id or not str(self.doc_id).strip():
            raise ValueError(f"Document.doc_id must be non-empty, got {self.doc_id!r}")
        if self.text is None:
            raise ValueError("Document.text must not be None")


@dataclass(slots=True)
class ScoredDoc:
    """A document plus its BM25 score and 1-based rank (C-02). ``score >= 0`` and
    ``rank >= 1`` (I-002: the ranked list is deterministic). ``truncated`` is set when
    the builder cut this doc's text to fit the token budget (E-05)."""

    doc: Document
    score: float
    rank: int
    truncated: bool = False

    def __post_init__(self) -> None:
        if self.score < 0.0:
            raise ValueError("ScoredDoc.score must be >= 0")
        if self.rank < 1:
            raise ValueError("ScoredDoc.rank must be >= 1")


@dataclass(slots=True)
class Context:
    """The token-bounded assembled text the LLM actually sees (C-03 / §14 / §3).

    ``docs`` are the included ScoredDocs in include-order (== ``provenance`` order);
    ``prompt`` carries a ``[doc_id]`` source label per included doc; ``provenance`` lists
    the included doc ids; ``tokens == est_tokens(prompt) <= token_budget`` (the I-005/
    I-006 invariant, "report ≡ build"); ``truncated`` is True iff any doc was dropped or
    cut to fit the budget (E-05/E-06/I-004).
    """

    docs: list[ScoredDoc]
    prompt: str
    provenance: list[str]
    tokens: int
    truncated: bool

    @property
    def empty(self) -> bool:
        """True when nothing fit (E-02): the answer cannot be grounded."""
        return len(self.docs) == 0


@dataclass(slots=True)
class Question:
    """A grounded question with its ``§15`` / ``§18`` ground truth (R-10).

    ``gold_answer`` is the reference answer (exact-match / reference-based eval, §19);
    ``relevant_docs`` are the ground-truth doc ids -- the TP/FN universe for precision/
    recall (§18); ``tier`` is one of the §17 difficulty tiers.
    """

    q_id: str
    question: str
    gold_answer: str
    relevant_docs: list[str]
    tier: str = "easy"

    # The §17 difficulty tiers (R-10). ``distractor`` is the interesting regime (§6/§7,
    # §17): lexically-similar-but-irrelevant docs that pull precision down.
    EASY = "easy"
    MULTI = "multi"
    SYNTHESIS = "synthesis"
    DISTRACTOR = "distractor"
    TIERS = (EASY, MULTI, SYNTHESIS, DISTRACTOR)

    def __post_init__(self) -> None:
        if self.tier and self.tier not in self.TIERS:
            raise ValueError(
                f"unknown tier {self.tier!r}; expected one of {self.TIERS}"
            )
        if any(r is None or str(r).strip() == "" for r in self.relevant_docs):
            raise ValueError("Question.relevant_docs must contain only non-empty ids")


@dataclass
class Answer:
    """A grounded, structured answer (C-04 / §19). Produced by the LLM, schema-validated.

    ``text`` is the free-form answer; ``confidence`` in [0,1]; ``sources`` are the doc_ids
    the model claims to cite -- the *harness* enforces these are a subset of the retrieved
    ``Context.provenance`` (I-003 / E-08); ``status`` is ``"COMPLETED"`` (validated) or
    ``"ERROR"`` (parse/validation exhausted).
    """

    q_id: str
    text: str
    confidence: float
    sources: list[str] = field(default_factory=list)
    usage: Usage = field(default_factory=lambda: Usage(0, 0))
    status: str = "COMPLETED"


@dataclass
class Verdict:
    """An LLM-as-judge verdict (C-06 / §19/§20).

    ``supported`` is True only when every factual claim in the answer is grounded in the
    retrieved context; ``complete`` when all of the question's relevant docs are reflected;
    ``unsupported_claims`` and ``total_factual_claims`` drive the hallucination rate
    (§20, R-09); ``status`` is ``"JUDGED"`` (validated), ``"ERROR"`` (exhausted), or
    ``"SKIPPED"`` (``--judge off``).
    """

    q_id: str
    correct: bool | None
    supported: bool | None
    complete: bool | None
    unsupported_claims: list[str]
    total_factual_claims: int
    rationale: str
    status: str = "JUDGED"


@dataclass
class RunMetrics:
    """All per-case metrics (C-07). Retrieval fields are populated for *every* case that
    cleared ``RETRIEVING`` (I-008 / R-12) so a later failure still yields a full retrieval
    diagnosis. Terminal ``status`` is ``SCORED`` / ``PARTIAL`` / ``ERROR`` (§3.1)."""

    q_id: str
    tier: str
    # -- retrieval (populated iff the case cleared RETRIEVING) --
    retrieved: list[str] = field(default_factory=list)  # doc_ids, in rank order
    expected: list[str] = field(default_factory=list)  # == question.relevant_docs
    tp: int = 0
    fp: int = 0
    fn: int = 0
    precision: float | None = None  # TP/(TP+FP); None when TP+FP==0 (I-007/E-02/E-03)
    recall: float | None = None  # TP/(TP+FN); None when TP+FN==0 (I-007)
    f1: float | None = None  # 2PR/(P+R) when P+R>0 else 0.0 (E-04/I-007)
    context_tokens: int = 0
    truncated: bool = False
    grounding_violation: bool = False  # E-08: foreign source ids were stripped
    # -- answer + judge (populated if generation/judging ran) --
    answer_status: str = "COMPLETED"  # "COMPLETED" | "ERROR"
    correct: bool | None = None
    supported: bool | None = None
    complete: bool | None = None
    unsupported_claims: int = 0
    total_factual_claims: int = 0
    # -- diagnostics / timing --
    failure_stage: str | None = (
        None  # None | retrieval|context|generation|judging|cancelled
    )
    retrieve_ms: float = 0.0
    generate_ms: float = 0.0
    total_latency_ms: float = 0.0
    status: str = "SCORED"  # "SCORED" | "PARTIAL" | "ERROR"


@dataclass
class AggregateMetrics:
    """Dataset-level metrics (C-07 / §21). Pure record: means are computed by
    ``metrics.aggregate`` and stored here, so this stays a headless dataclass.

    Means are over the relevant rows only; ``hallucination_rate`` uses the
    no-division-by-zero guard (I-007); ``by_tier`` holds one sub-aggregate per populated
    §17 tier (I-012).
    """

    n_cases: int
    precision: float
    recall: float
    f1: float
    answer_accuracy: float  # mean(correct) over JUDGED rows (R-08)
    hallucination_rate: float  # sum(unsupported)/sum(total) over JUDGED rows (R-09)
    failure_breakdown: dict[str, int] = field(
        default_factory=dict
    )  # stage -> count (R-12)
    by_tier: dict[str, "AggregateMetrics"] = field(default_factory=dict)


__all__ = [
    "AggregateMetrics",
    "Answer",
    "Context",
    "Document",
    "Question",
    "RunMetrics",
    "ScoredDoc",
    "Usage",
    "Verdict",
]

# --- Usage is referenced above but defined below to keep the read order natural ---


@dataclass(slots=True)
class Usage:
    """Token usage for a single LLM role (ch1 C-01 usage). Both counts >= 0 (I-001)."""

    prompt_tokens: int
    completion_tokens: int

    def __post_init__(self) -> None:
        if self.prompt_tokens < 0 or self.completion_tokens < 0:
            raise ValueError("token counts must be >= 0")

    @property
    def total_tokens(self) -> int:
        """I-001: total is the sum of the two component counts."""
        return self.prompt_tokens + self.completion_tokens
