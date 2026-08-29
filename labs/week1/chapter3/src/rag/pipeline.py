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
        len(vs._data), strategy, contextual, mock, embed_model,
        )
    return vs, bm


def _query_embedder() -> Embedder:
    """Deterministic query embedder (F-016: mock seed-independent)."""
    return MockEmbedder()


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
    """Query-time pipeline for one question (R-15) -> RunMetrics (R-14)."""
    t0 = time.perf_counter()
    vs, bm = index
    query_text = question.question

    retriever = HybridRetriever(
        store=vs, bm25=bm, cfg=HybridConfig(alpha=alpha), candidates=top_n,
        )
    q_vec = _query_embedder().embed(query_text)
    t_r0 = time.perf_counter()
    if hybrid:
        raw = retriever.retrieve(q_vec, query_text, candidates=top_n)
    else:
        raw = vs.search(q_vec, top_n)
    retrieve_ms = (time.perf_counter() - t_r0) * 1000.0

    if expand and n_expand > 0:
        expander = MockQueryExpander()
        def fetch(q: str, candidates: int) -> list[ScoredChunk]:
            qv = _query_embedder().embed(q)
            if hybrid:
                return (retriever.retrieve(qv, q, candidates=candidates))
            return vs.search(qv, candidates)
        raw = multi_query(expander, fetch, query_text, n=n_expand, candidates=top_n)

    if rerank:
        t_rr0 = time.perf_counter()
        reranked = MockReranker().rerank(query_text, raw, top_k=top_k)
        rerank_ms = (time.perf_counter() - t_rr0) * 1000.0
    else:
        reranked = raw
        rerank_ms = 0.0

    ctx = build_context(reranked, token_budget=8192)
    chunk_list = list(ctx.docs)[:top_k]
    context_str = " ".join(sc.chunk.text for sc in chunk_list)

    citer = Citer()
    provenance = {sc.chunk.chunk_id for sc in chunk_list}
    injection_result: InjectionResult = citer.scan_injection(chunk_list)

    t_g0 = time.perf_counter()
    llm = llm if llm is not None else MockLLM()
    answer = llm.generate(
        system="You are a precise, well-cited assistant.",
        context=context_str,
        question=query_text,
        schema={"question": question.q_id},
        seed=42,
        )
    generate_ms = (time.perf_counter() - t_g0) * 1000.0

    citation_result: CitationResult = citer.grounding_gate(answer, provenance)

    verdict = None
    if judge is not None:
        verdict = judge.judge(
            question=question,
            context=context_str,
            answer=answer,
            claims=citer.extract_claims(answer.text),
            gold_facts=question.gold_facts,
            on_failure="empty",
            )

    retrieved_ids = [sc.chunk.chunk_id for sc in chunk_list]
    rel = set(question.relevant_chunks or [])
    m = RunMetrics(
        q_id=question.q_id,
        tier=question.tier,
        retrieved=retrieved_ids,
        expected=list(question.relevant_chunks or []),
        precision=precision(rel, retrieved_ids, top_k),
        recall=recall(rel, retrieved_ids, top_k),
        mrr=mrr(rel, retrieved_ids, 10),
        ap=ap(rel, retrieved_ids, top_k),
        ndcg=ndcg(rel, retrieved_ids, top_k),
        context_tokens=ctx.tokens,
        truncated=ctx.truncated,
        answer_status=answer.status,
        injection_warning=injection_result.injection_warning,
        grounding_violation=citation_result.grounding_violation,
        retrieve_ms=round(retrieve_ms, 4),
        rerank_ms=round(rerank_ms, 4),
        generate_ms=round(generate_ms, 4),
        total_latency_ms=round((time.perf_counter() - t0) * 1000.0, 4),
        status="SCORED",
        )
    if verdict is not None:
        m.correct = verdict.correct
        m.supported = verdict.supported
        m.complete = verdict.complete
        m.faithfulness = verdict.faithfulness
        m.completeness = verdict.completeness
        m.citation_quality = verdict.citation_quality
        m.unsupported_claims = verdict.unsupported_claims
        m.injection_warning = verdict.injection_warning
        m.which_field_decided = verdict.which_field_decided
    logger.debug("run_case {} tier={} recall={}", question.q_id, question.tier, m.recall)
    return m


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
                q, index,
                hybrid=hybrid, alpha=alpha, rerank=rerank, top_n=top_n,
                top_k=top_k, expand=expand, n_expand=n_expand,
                judge=judge, llm=llm, cfg=cfg,
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
