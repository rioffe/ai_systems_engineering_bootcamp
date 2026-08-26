"""RAG Eval Harness (SPEC §5.1) -- a deterministic retrieval + context + metrics pipeline
with an LLM-as-judge, run over a grounded question dataset.

The **deterministic boundary** (retrieval, context construction, metrics, corpus) is
pure stdlib and needs no LLM/Ollama/network (SPEC R-17 / I-009). The two probabilistic
roles -- answer generation and judging -- are isolated behind the `LLM` / `Judge`
interfaces and replaced offline by deterministic `MockLLM` / `MockJudge` doubles
(SPEC R-14 / I-011), so the entire test suite runs fully offline.

Public surface (see SPEC §11 traceability):
- types        C-01 / C-04 / C-07 record types
- corpus       C-01 load_corpus / load_questions / generate_corpus_and_questions
- retrieval    C-02 BM25Retriever
- context      C-03 build_context + est_tokens
- metrics      C-07 retrieval_pr + aggregate
- schemas      C-05 answer/verdict JSON-Schema + parse/validate/retry
- model        C-05 LLM / MockLLM / OllamaLLM
- judgment     C-06 Judge / MockJudge / OllamaJudge
- pipeline     run_case / run_dataset (state machine §3.1, failure attribution R-12)
- cli          §5.1 `rag-eval` (eval / gen-corpus / show)
- app          process entry point
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
