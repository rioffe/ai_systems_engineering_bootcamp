"""Pipeline: the §13 wiring -- retrieve -> context -> generate -> judge -> metrics.

This layer turns the deterministic boundary (retrieval, context, metrics) and the two
probabilistic roles (generation, judging) into a per-case eval and a dataset-level report
(R-11/R-12). It implements the §3.1 case state machine and its failure-attribution
contract (I-008): a fault at any stage names exactly one ``failure_stage`` and still
yields a complete retrieval diagnosis for stages already cleared.

The E-08 grounding gate strips a foreign citation, forces ``supported`` False, and counts
the claim -- enforced here, *not* trusted to the model. Backend faults (Ollama unreachable
/ model not found, E-11/E-12) propagate out of ``run_case`` so the CLI can map them to an
exit code; a case-level parse/validation fault is *recorded* as an ERROR/PARTIAL row and
the run continues (the run-all default).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

from .context import build_context
from .judgment import Judge
from .metrics import aggregate, retrieval_pr
from .model import LLM, ModelNotFoundError, OllamaError
from .retrieval import BM25Retriever
from .schemas import DEFAULT_MAX_RETRIES
from .types import (
    AggregateMetrics,
    Answer,
    Context,
    Question,
    RunMetrics,
    ScoredDoc,
    Verdict,
)


@dataclass
class CaseRun:
    """The full per-case result: the metric ``row`` plus the artifacts ``show`` prints.

    ``row`` is what ``aggregate`` consumes; the rest (retrieval ranking, the built
    context, the grounded answer, and the verdict) feed the §5.1 ``show`` diagnostic.
    """

    row: RunMetrics
    question: Question
    retrieved: list[ScoredDoc]
    context: Context | None
    answer: Answer | None
    verdict: Verdict | None

    def to_detail(self) -> dict:
        """A serializable §5.1 ``show`` snapshot of this case."""
        return _case_detail(self)


@dataclass
class RunReport:
    """A dataset-level report: per-case rows, the aggregate, and the run's meta (R-11)."""

    cases: list[CaseRun]
    aggregate: AggregateMetrics
    meta: dict = field(default_factory=dict)

    @property
    def rows(self) -> list[RunMetrics]:
        return [c.row for c in self.cases]

    def to_dict(self) -> dict:
        return {
            "meta": self.meta,
            "aggregate": asdict(self.aggregate),
            "cases": [c.to_detail() for c in self.cases],
        }


def _empty_context() -> Context:
    return Context(docs=[], prompt="", provenance=[], tokens=0, truncated=False)


def _total(row: RunMetrics, start: float) -> None:
    row.total_latency_ms = (time.perf_counter() - start) * 1000


def run_case(
    question: Question,
    retriever: BM25Retriever,
    llm: LLM,
    judge: Judge,
    *,
    k: int = 5,
    token_budget: int = 2000,
    judge_on: bool = True,
    seed: int = 42,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> CaseRun:
    """Run one question through the full §13 pipeline (state machine, §3.1).

    A pre-terminal stage fault is recorded with its ``failure_stage`` (I-008): a
    generation fault is an ERROR, a judge fault is PARTIAL (retrieval intact). Backend
    faults (OllamaError/ModelNotFoundError) propagate. A judge-off case is a retrieval-
    only eval: its verdict is SKIPPED and its judgment fields are None.
    """
    start = time.perf_counter()
    row = RunMetrics(
        q_id=question.q_id,
        tier=question.tier,
        expected=list(question.relevant_docs),
    )

    # -- RETRIEVING (deterministic) --
    scored: list[ScoredDoc]
    try:
        t = time.perf_counter()
        scored = retriever.search(question.question, k)
        row.retrieve_ms = (time.perf_counter() - t) * 1000
        row.retrieved = [sd.doc.doc_id for sd in scored]
        tp, fp, fn, p, r, f1 = retrieval_pr(question.relevant_docs, row.retrieved)
        row.tp, row.fp, row.fn = tp, fp, fn
        row.precision, row.recall, row.f1 = p, r, f1
    except (OllamaError, ModelNotFoundError):
        raise  # fatal backend fault -> the CLI maps this to an exit code
    except Exception:
        row.failure_stage = "retrieval"
        row.status = "ERROR"
        _total(row, start)
        return CaseRun(row, question, [], _empty_context(), None, None)

    # -- CONTEXTING (deterministic, token-bounded) --
    context: Context
    try:
        context = build_context(scored, token_budget=token_budget)
        row.context_tokens = context.tokens
        row.truncated = context.truncated
    except Exception:
        row.failure_stage = "context"
        row.status = "ERROR"
        _total(row, start)
        return CaseRun(row, question, scored, _empty_context(), None, None)

    # -- GENERATING (the one probabilistic step) --
    answer: Answer
    try:
        t = time.perf_counter()
        answer = llm.generate(
            system="Ground a concise answer in the retrieved documents only.",
            context=context.prompt,
            question=question.question,
            seed=seed,
            max_retries=max_retries,
        )
        row.generate_ms = (time.perf_counter() - t) * 1000
    except (OllamaError, ModelNotFoundError):
        raise
    except Exception:
        row.failure_stage = "generation"
        row.status = "ERROR"
        row.answer_status = "ERROR"
        _total(row, start)
        return CaseRun(row, question, scored, context, None, None)

    # A generation that exhausts its parse retries returns status "ERROR" (not a raised
    # exception): record it as a generation fault with the retrieval intact (I-008).
    if answer.status == "ERROR":
        row.failure_stage = "generation"
        row.status = "ERROR"
        row.answer_status = "ERROR"
        _total(row, start)
        return CaseRun(row, question, scored, context, answer, None)

    # -- E-08 grounding gate: strip a foreign citation, force supported False, count it --
    provenance = set(context.provenance)
    raw_sources = list(answer.sources)
    foreign = [s for s in raw_sources if s not in provenance]
    grounding_violation = bool(foreign)
    if grounding_violation:
        answer.sources = [s for s in raw_sources if s in provenance]
        row.grounding_violation = True
    row.answer_status = "COMPLETED"

    # -- JUDGING (the second probabilistic step, skippable via --judge off) --
    verdict: Verdict | None = None
    if judge_on:
        try:
            verdict = judge.judge(
                question=question,
                context=context,
                answer=Answer(
                    q_id=question.q_id,
                    text=answer.text,
                    confidence=answer.confidence,
                    sources=list(raw_sources),  # the judge sees the RAW citations
                    usage=answer.usage,
                    status=answer.status,
                ),
                max_retries=max_retries,
            )
        except Exception:
            verdict = Verdict(
                q_id=question.q_id,
                correct=None,
                supported=None,
                complete=None,
                unsupported_claims=[],
                total_factual_claims=0,
                rationale="",
                status="ERROR",
            )
        assert verdict is not None
        if verdict.status == "ERROR":
            row.failure_stage = "judging"
            row.status = "PARTIAL"
            _total(row, start)
            return CaseRun(row, question, scored, context, answer, verdict)
        row.correct = verdict.correct
        row.supported = verdict.supported
        row.complete = verdict.complete
        row.unsupported_claims = len(verdict.unsupported_claims)
        row.total_factual_claims = verdict.total_factual_claims
        if grounding_violation:  # I-003: the harness forces supported False
            row.supported = False
    else:
        verdict = Verdict(
            q_id=question.q_id,
            correct=None,
            supported=None,
            complete=None,
            unsupported_claims=[],
            total_factual_claims=0,
            rationale="--judge off",
            status="SKIPPED",
        )
        if grounding_violation:  # the gate still fires in retrieval-only mode
            row.supported = False
            row.unsupported_claims = len(foreign)
            row.total_factual_claims = len(raw_sources)

    row.status = "SCORED"
    _total(row, start)
    return CaseRun(row, question, scored, context, answer, verdict)


def run_dataset(
    questions: list[Question],
    retriever: BM25Retriever,
    llm: LLM,
    judge: Judge,
    *,
    k: int = 5,
    token_budget: int = 2000,
    judge_on: bool = True,
    tiers: set[str] | None = None,
    stop_on_error: bool = False,
    seed: int = 42,
    max_retries: int = DEFAULT_MAX_RETRIES,
    meta: dict | None = None,
    on_progress: Callable[[Question, RunMetrics], object] | None = None,
) -> RunReport:
    """Run the whole dataset, honouring tier filtering, --stop-on-error, --judge off.

    Returns a :class:`RunReport` whose rows aggregate to a per-tier breakdown (§9.5/R-11).
    A backend fault propagates; every other case fault is recorded and the run continues
    (run-all default) unless ``stop_on_error`` is set (§3.1).
    """
    selected = [q for q in questions if tiers is None or q.tier in tiers]

    cases: list[CaseRun] = []
    for question in selected:
        case = run_case(
            question,
            retriever,
            llm,
            judge,
            k=k,
            token_budget=token_budget,
            judge_on=judge_on,
            seed=seed,
            max_retries=max_retries,
        )
        cases.append(case)
        if on_progress is not None:
            on_progress(question, case.row)
        if stop_on_error and case.row.status in ("ERROR", "PARTIAL"):
            break
    return RunReport(
        cases=cases,
        aggregate=aggregate([c.row for c in cases]),
        meta=meta or {},
    )


def _case_detail(case: CaseRun) -> dict:
    """Build the §5.1 ``show`` snapshot from a finished :class:`CaseRun`."""
    question = case.question
    context = case.context
    ranked = [
        {
            "doc_id": sd.doc.doc_id,
            "rank": sd.rank,
            "score": round(sd.score, 4),
            "truncated": sd.truncated,
        }
        for sd in case.retrieved
    ]
    out: dict = {
        "q_id": question.q_id,
        "tier": question.tier,
        "question": question.question,
        "gold_answer": question.gold_answer,
        "relevant_docs": list(question.relevant_docs),
        "retrieved": ranked,
        "context_tokens": context.tokens if context is not None else 0,
        "context_truncated": context.truncated if context is not None else False,
        "provenance": list(context.provenance) if context is not None else [],
        "metrics": asdict(case.row),
        "answer": None,
        "verdict": None,
    }
    if case.answer is not None:
        out["answer"] = {
            "text": case.answer.text,
            "confidence": case.answer.confidence,
            "sources": list(case.answer.sources),
            "status": case.answer.status,
        }
    if case.verdict is not None:
        out["verdict"] = _verdict_json(case.verdict)
    return out


def _verdict_json(verdict: Verdict) -> dict:
    return {
        "q_id": verdict.q_id,
        "correct": verdict.correct,
        "supported": verdict.supported,
        "complete": verdict.complete,
        "unsupported_claims": list(verdict.unsupported_claims),
        "total_factual_claims": verdict.total_factual_claims,
        "rationale": verdict.rationale,
        "status": verdict.status,
    }


__all__ = [
    "CaseRun",
    "RunReport",
    "run_case",
    "run_dataset",
]
