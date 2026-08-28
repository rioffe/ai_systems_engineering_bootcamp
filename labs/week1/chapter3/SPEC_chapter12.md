## 11. Traceability matrix (id → where realized)

```text
§0 / §2 thesis         --> pipeline.py (build_index/run_case/run_dataset)      --> T-03, §9.11
R-01                   --> pipeline.py build_index + run_case                  --> T-01, T-03, T-13
R-02 / I-002           --> C-02 OllamaEmbedder/MockEmbedder + VectorStore/cosine + O-1b  --> T-03, T-04
R-03 / I-013 (§14/§14) --> chunking.py Fixed/Heading/Contextual + boundary_guard   --> T-21, E-07
R-04 / O-3             --> C-04 HybridRetriever (α·minmax sem + (1−α)·minmax lex) --> T-07
R-05 (§9)              --> C-05 MockReranker/LLMReranker top-N -> top-k         --> T-23
R-06 (§10/§11/§19)     --> C-06 MockQueryExpander + multi_query union/dedupe     --> T-23, T-04b
R-07 / I-007 (§12)     --> C-07 contextualize (embed_text prefix; text shown)   --> T-20
R-08 / I-003 (§13/§21) --> citation.py Citer grounding gate (drop foreign ids)   --> T-08c, E-08
R-09 / I-010           --> model.py OllamaLLM/MockLLM + schemas/answer.json      --> T-08
R-10 / I-010 (§19)     --> judgment.py OllamaJudge/MockJudge + schemas/verdict.json --> T-08, T-08a
R-11 / I-001 (§20)     --> metrics.py P/R@k, MRR, MAP, NDCG + worked example     --> T-05a, T-05b
R-12 / I-007 (§21)     --> metrics.py faithfulness/completeness/citation_quality --> T-08a
R-13 (§14-§19 tiers)   --> corpus.generate_corpus_and_questions (7 tiers)        --> T-01, T-01b
R-14 (§22 per-cap diff) --> cli.py eval: report by_tier + by_capability           --> T-08b, §9.5
R-15 / I-008 (§21)     --> RunMetrics.failure_stage + PARTIAL semantics          --> T-10, E-15
R-16 (§5.2 GUI)        --> ui.py (offscreen, ch1/ch2 analog)                     --> T-16, E-17
R-17 / I-011           --> Mock* doubles + pyproject (uv)                        --> T-14
R-18 / I-002           --> seed threading (corpus + mock paths)                 --> T-01, T-03, T-04, T-23
R-19 / E-13            --> embedding.py/model.py model discovery + fallback       --> E-13, E-14
R-20 / I-009           --> no-LLM/network layers source scan                     --> T-02
R-21 (§18)             --> citation.py injection scan (data, not instructions)   --> T-17, E-16
R-22 (metadata §7)     --> ChunkMetadata + which_doc_decided                     --> T-17, E-09, E-10
I-004/I-005/I-006      --> context.py build_context + est_tokens (single formula) --> T-06, T-06b, T-11
I-007 (§20/§21)        --> metrics.py no-division-by-zero guards                 --> T-05b, T-08a
I-012                  --> metrics.py aggregate (by_tier + by_capability)         --> T-08b
I-013 / E-14           --> load_corpus/load_questions integrity check            --> T-15
§15 distractor         --> distractor tier + E-03/E-08                          --> T-01b, T-17
§16 conflict / §17 recency --> version/updated_at resolution + which_doc_decided  --> E-09, E-10, T-17
§18 injection          --> Citer injection scan + report banner                  --> E-16, R-21, T-17
§19 multi-hop          --> multi tier + expand raise                             --> T-04b, E-15
§21 "where did it fail" --> --judge off ablation + failure_stage                 --> R-15, T-10
§25 vs traditional search --> --mock vs --model diff in by_capability            --> §9.11
K-01 / I-011           --> offline full suite (no Ollama/embed)                 --> T-14
K-02                   --> performance smoke (< 5s dense boundary)              --> T-13
K-05                   --> real end-to-end smoke (opt-in manual)                --> §9.11
```

**Open questions / ambiguities flagged for the human (spec elicitation):**

1. **Vector index backend.** Spec picks an **in-memory pure-Python `VectorStore`** (cosine, stdlib `math`); an optional `numpy` accelerator and a hosted/embedded vector DB (faiss/pgvector/Qdrant) are out-of-scope extensions behind the *same* `VectorStore` interface (Q-03). *Confirm* in-memory is acceptable for v0.1.
2. **Answer + verdict schemas.** Both are fixed JSON-Schema objects for v0.1 (ch1/ch2 Q-02 analog): answer `{answer, confidence, citations[], status}`; verdict `{correct, supported, complete, unsupported_claims, total_factual_claims, faithfulness, completeness, citation_quality, injection_warning, grounding_violation, which_doc_decided, rationale, status}`. *Confirm* these shapes; `citations` may be empty when the answer is "I cannot answer from the provided documents" — *confirm* empty `citations` is allowed (`minItems:0`).
3. **Reranker default.** `MockReranker` (0.6·coverage + 0.4·norm-cosine) is the default; `LLMReranker` (same `qwen3.8:27b-mlx`, opt-in) replaces it; a cross-encoder is out of scope behind the `Reranker` interface (Q-01). *Confirm* the rerank role is LLM-based (not a learned cross-encoder) for v0.1.
4. **Token estimator.** `est_tokens = ceil(len(s)/4)` (approx; deterministic, single formula, I-005) — *confirm* this vs. a real tokenizer (out of scope for v0.1: it would introduce a model dependency into the deterministic boundary, contradicting I-009; Q-04).
5. **Concurrency.** v0.1 is **strictly sequential** per case (one shared `qwen3.8:27b-mlx` slot; deterministic and simplest). `--concurrency N` is deferred (Q-05).
6. **State/memory extension.** A cross-question state/memory subsystem is explicitly **out of scope** for v0.1 (Q-06): the corpus + question set are static per run; the only cross-stage state is the retrieval trace that becomes the report row. *Confirm* no persistence between questions is needed.
7. **Ground truth in a synthetic corpus.** `gen-corpus` authors the `question ↔ relevant_chunks`/`gold_facts` mapping deterministically so the §20/§21 metrics have a meaningful denominator. *Confirm* this is acceptable as the v0.1 eval baseline (Q-07) vs. hand-authoring a curated ~10-doc + a few-question starter set first to sanity-check before scaling to ~100.
8. **Semantic chunking.** `SemanticChunker` is an optional/extension strategy (Q-04); v0.1 ships `Fixed` (baseline, for the §14 boundary experiment) and `Heading` (default per §6) plus `Contextual`. *Confirm* semantic chunking stays deferred.
9. **Report format.** v0.1 emits JSON (`report.json`) with `by_tier` + `by_capability` + `failure_breakdown` plus a human summary to stdout (Q-08). *Confirm* no richer format (HTML/CSV dashboard) is needed for v0.1.

---
*End of specification. This document is the source of truth; implementation and tests are to be
derived from it and kept in sync per §11. v0.1 covers §1–§28 of `curriculum/week1/chapter3.md`
(dense + hybrid retrieval, rerank, query expansion, contextual retrieval, cited generation, and
the retrieval-vs-generation evaluation stack, with the §14–§19 failure modes as measurable tiers).*
