"""Pipeline: build_index + run_case + run_dataset (C-12, R-01/R-14/R-15)."""

from __future__ import annotations

import time
from typing import Any

from loguru import logger

from rag.chunking import ContextualChunker, FixedChunker, HeadingChunker
from rag.citation import CitationResult, Citer, InjectionResult
from rag.context import build_context
from rag.embedding import Embedder, MockEmbedder
from rag.expand import MockQueryExpander, multi_query
from rag.judgment import Judge
from rag.metrics import ap, mrr, ndcg, precision, recall
from rag.model import LLM, MockLLM
from rag.retrieval import (
    BM25Index,
    HybridConfig,
    HybridRetriever,
    MockReranker,
    VectorStore,
)
from rag.schemas import validate_answer, validate_verdict
from rag.types import RunMetrics, ScoredChunk


def _make_chunker(strategy: str, chunk_size: int, overlap: int) -> Any:
    if strategy == "fixed":
        return FixedChunker(chunk_size=chunk_size, overlap=overlap)
    if strategy == "heading":
        return HeadingChunker(chunk_size=chunk_size, overlap=overlap)
    if strategy == "contextual":
        return ContextualChunker(chunk_size=chunk_size, overlap=overlap)
    raise ValueError(f"Unknown chunking strategy: {strategy}")


def build_index(
    docs,
    *,
    strategy: str = "fixed",
    contextual: bool = False,
    embedder: Embedder | None = None,
    overlap: int = 10,
    chunk_size: int = 50,
    embed_model: str = "mock",
    mock: bool = True,
) -> tuple[VectorStore, BM25Index]:
    """Index-time (R-01): chunk -> contextualize -> embed -> insert."""
    emd = embedder or MockEmbedder()
    chunker = _make_chunker(strategy, chunk_size, overlap)
    vs = VectorStore(dim=emd.dim)
    bm = BM25Index(dim=emd.dim)
    vs._data = {}
    bm._data = {}
    for doc in docs:
        for chunk in chunker.chunk(doc, overlap=overlap):
            ctx_text = chunk.text
            if contextual and chunk.meta:
                title = chunk.meta.title or chunk.meta.doc_id
                section = chunk.meta.section or ""
                ctx_text = f"Document: {title} / Section: {section}"
                ctx_text = ctx_text + " " + chunk.text
            embed_text = ctx_text if contextual else chunk.text
            vec = emd.embed(embed_text)
            vs.insert(chunk, vec)
            vs._data[chunk.chunk_id] = (chunk, vec)
            bm._data[chunk.chunk_id] = chunk
    all_chunks = [pair[0] for pair in vs._data.values()]
    bm.index(all_chunks)
    logger.info(
        "build_index: {} chunks strategy={} contextual={} mock={} model={}",
        len(vs._data),
        strategy,
        contextual,
        mock,
        embed_model,
    )
    return vs, bm


def _query_embedder() -> Embedder:
    """Deterministic query embedder (F-016: mock seed-independent)."""
    return MockEmbedder()


# -- terminal-state helpers (I-008: exactly one failure_stage) --------------


def _score_case(m: RunMetrics, t0: float) -> RunMetrics:
    """All stages ok -> SCORED; no failure_stage (I-008)."""
    m.status = "SCORED"
    m.total_latency_ms = round((time.perf_counter() - t0) * 1000.0, 4)
    logger.debug("run_case {} -> SCORED", m.q_id)
    return m


def _fail_case(m: RunMetrics, stage: str, err: BaseException | str, t0: float) -> RunMetrics:
    """A stage before judging terminal-faulted -> ERROR naming that ONE stage
    (I-008/R-15); the deterministic boundary never fabricates a stage."""
    m.failure_stage = stage
    m.status = "ERROR"
    m.total_latency_ms = round((time.perf_counter() - t0) * 1000.0, 4)
    logger.warning("run_case {} -> ERROR (failure_stage={}): {}", m.q_id, stage, err)
    return m


def _partial_case(m: RunMetrics, err: BaseException | str, t0: float) -> RunMetrics:
    """Judge failed after a successful generate (E-11) -> PARTIAL: the
    retrieval + generation diagnosis is intact; only the generation-QA metrics
    (from the verdict) are absent, and failure_stage == 'judging'."""
    m.failure_stage = "judging"
    m.status = "PARTIAL"
    m.total_latency_ms = round((time.perf_counter() - t0) * 1000.0, 4)
    logger.warning("run_case {} -> PARTIAL (failure_stage=judging): {}", m.q_id, err)
    return m


def run_case(
    question,
    index,
    *,
    hybrid: bool = True,
    alpha: float = 0.5,
    rerank: bool = False,
    top_n: int = 50,
    top_k: int = 5,
    expand: bool = False,
    n_expand: int = 0,
    judge: Judge | None = None,
    llm: LLM | None = None,
    cfg: Any = None,
) -> RunMetrics:
    """Query-time (§3.2) state machine over the *pre-built* `index` (R-14/R-15).

    RETRIEVE -> (EXPAND) -> (RERANK) -> CONTEXT -> CITE -> GENERATE -> (JUDGE)
    -> metrics. Per §3.2 / I-008 / R-15, a terminal `ERROR`/`PARTIAL` names
    exactly ONE `failure_stage`; the retrieval-stage fields are populated for any
    case that cleared `RETRIEVING`, so a later-stage fault still yields a COMPLETE
    retrieval diagnosis (§21 "where did it fail?").

    - generation/judge fault -> ERROR (`failure_stage='generation'`) or PARTIAL
      (`failure_stage='judging'`, E-11) with the retrieval diagnosis intact.
    - `judge is None` (--judge off, E-12): the JUDGING stage is skipped; the
      generation-QA metrics stay `None` and the case SCORES retrieval-only.
    """
    t0 = time.perf_counter()
    vs, bm = index
    query_text = question.question
    m = RunMetrics(q_id=question.q_id, tier=question.tier)

    # capability_flags drives AggregateMetrics.by_capability (I-012 / T-08b):
    # which query-time §22 toggles are ON for this run. Population happens here,
    # before any stage fault, so a FAILED run still carries its flags and the
    # by_capability diff is never dead. (Index-time caps -- --contextual/
    # --strategy -- are set at build_index, not here.)
    m.capability_flags = {
        "hybrid": bool(hybrid),
        "rerank": bool(rerank),
        "expand": bool(expand and n_expand > 0),
    }

    # -- RETRIEVE -----------------------------------------------------------
    retriever = HybridRetriever(
        store=vs,
        bm25=bm,
        cfg=HybridConfig(alpha=alpha),
        candidates=top_n,
    )
    q_vec = _query_embedder().embed(query_text)
    t_r0 = time.perf_counter()
    try:
        if hybrid:
            raw = retriever.retrieve(q_vec, query_text, candidates=top_n)
        else:
            raw = vs.search(q_vec, top_n)
    except Exception as exc:  # noqa: BLE001 -- attribute, never fabricate
        return _fail_case(m, "retrieval", exc, t0)
    retrieve_ms = (time.perf_counter() - t_r0) * 1000.0

    # -- EXPAND (opt-in) ----------------------------------------------------
    if expand and n_expand > 0:
        expander = MockQueryExpander()

        def fetch(q: str, candidates: int) -> list[ScoredChunk]:
            qv = _query_embedder().embed(q)
            if hybrid:
                return retriever.retrieve(qv, q, candidates=candidates)
            return vs.search(qv, candidates)

        try:
            raw = multi_query(expander, fetch, query_text, n=n_expand, candidates=top_n)
        except Exception as exc:  # noqa: BLE001
            return _fail_case(m, "expansion", exc, t0)

    # -- RERANK (opt-in) ----------------------------------------------------
    if rerank:
        t_rr0 = time.perf_counter()
        try:
            reranked = MockReranker().rerank(query_text, raw, top_k=top_k)
        except Exception as exc:  # noqa: BLE001
            return _fail_case(m, "reranking", exc, t0)
        rerank_ms = (time.perf_counter() - t_rr0) * 1000.0
    else:
        reranked = raw
        rerank_ms = 0.0

    # -- CONTEXT + CITE -----------------------------------------------------
    try:
        ctx = build_context(reranked, token_budget=8192)
        chunk_list = list(ctx.docs)[:top_k]
        context_str = " ".join(sc.chunk.text for sc in chunk_list)
    except Exception as exc:  # noqa: BLE001
        return _fail_case(m, "context", exc, t0)

    # RETRIEVING cleared: populate the COMPLETE retrieval diagnosis NOW so a
    # later-stage fault still yields it (I-008 / §21 "did retrieval provide
    # the evidence?").
    citer = Citer()
    provenance = {sc.chunk.chunk_id for sc in chunk_list}
    injection_result: InjectionResult = citer.scan_injection(chunk_list)
    retrieved_ids: list[str] = [sc.chunk.chunk_id for sc in chunk_list]
    rel = set(question.relevant_chunks or [])
    m.retrieved = retrieved_ids
    m.expected = list(question.relevant_chunks or [])
    m.precision = precision(rel, retrieved_ids, top_k)
    m.recall = recall(rel, retrieved_ids, top_k)
    m.mrr = mrr(rel, retrieved_ids, 10)
    m.ap = ap(rel, retrieved_ids, top_k)
    m.ndcg = ndcg(rel, retrieved_ids, top_k)
    m.context_tokens = ctx.tokens
    m.truncated = ctx.truncated
    m.injection_warning = injection_result.injection_warning
    m.retrieve_ms = round(retrieve_ms, 4)
    m.rerank_ms = round(rerank_ms, 4)

    # -- GENERATE -----------------------------------------------------------
    t_g0 = time.perf_counter()
    active_llm = llm if llm is not None else MockLLM()
    try:
        answer = active_llm.generate(
            system="You are a precise, well-cited assistant.",
            context=context_str,
            question=query_text,
            schema={"question": question.q_id},
            seed=42,
        )
    except Exception as exc:  # noqa: BLE001
        m.generate_ms = round((time.perf_counter() - t_g0) * 1000.0, 4)
        return _fail_case(m, "generation", exc, t0)
    generate_ms = (time.perf_counter() - t_g0) * 1000.0
    m.answer_status = answer.status
    m.generate_ms = round(generate_ms, 4)

    # I-010: gate the emitted answer -- only a schema-valid object scores.
    try:
        validate_answer(answer)
    except Exception as exc:  # noqa: BLE001
        return _fail_case(m, "generation", exc, t0)

    citation_result: CitationResult = citer.grounding_gate(answer, provenance)
    m.grounding_violation = citation_result.grounding_violation
    if answer.status == "ERROR":  # E-11: generation terminal-faulted
        return _fail_case(m, "generation", answer.error or "generation failed", t0)

    # -- JUDGE (E-11 PARTIAL on judge fault; E-12 skip when --judge off) ---
    if judge is not None:
        try:
            verdict = judge.judge(
                question=question,
                context=context_str,
                answer=answer,
                claims=citer.extract_claims(answer.text),
                gold_facts=question.gold_facts,
                on_failure="empty",
            )
        except Exception as exc:  # noqa: BLE001
            return _partial_case(m, exc, t0)
        # I-010: gate the verdict -- only a schema-valid object scores.
        try:
            validate_verdict(verdict)
        except Exception as exc:  # noqa: BLE001
            return _partial_case(m, exc, t0)
        if verdict.status == "ERROR":  # E-11: judge exhausted its retries
            return _partial_case(m, verdict.rationale or "judge failed", t0)
        # record generation-QA metrics ONLY on a clean verdict; otherwise they
        # stay None so the "did the model use it" side is honestly absent.
        m.correct = verdict.correct
        m.supported = verdict.supported
        m.complete = verdict.complete
        m.faithfulness = verdict.faithfulness
        m.completeness = verdict.completeness
        m.citation_quality = verdict.citation_quality
        m.unsupported_claims = verdict.unsupported_claims
        m.injection_warning = verdict.injection_warning
        m.which_field_decided = verdict.which_field_decided

    return _score_case(m, t0)


def run_dataset(
    questions,
    index,
    *,
    hybrid: bool = True,
    alpha: float = 0.5,
    rerank: bool = False,
    top_n: int = 50,
    top_k: int = 5,
    expand: bool = False,
    n_expand: int = 0,
    judge: Judge | None = None,
    llm: LLM | None = None,
    cfg: Any = None,
) -> list[RunMetrics]:
    results: list[RunMetrics] = []
    for q in questions:
        try:
            m = run_case(
                q,
                index,
                hybrid=hybrid,
                alpha=alpha,
                rerank=rerank,
                top_n=top_n,
                top_k=top_k,
                expand=expand,
                n_expand=n_expand,
                judge=judge,
                llm=llm,
                cfg=cfg,
            )
        except (AttributeError, TypeError, ValueError, KeyError) as exc:
            qid = getattr(q, "q_id", None)
            if qid is None:
                qid = getattr(q, "doc_id", None)
            if qid is None:
                qid = str(q)
            logger.warning("run_dataset failed on {}: {}", qid, exc)
            m = RunMetrics(q_id=str(qid), tier="unknown", status="ERROR")
        results.append(m)
    return results
