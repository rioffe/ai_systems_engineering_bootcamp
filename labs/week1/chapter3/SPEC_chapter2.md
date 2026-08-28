## 1. Actors and goals

| Actor | Goals |
| --- | --------- |
| **User** (human, single process) | Run the eval (CLI) over the grounded question dataset; inspect a metrics report with a per-tier breakdown and a per-capability diff; and/or, in the optional GUI, type one question and see ranked→reranked→contextualized evidence (with scores), the grounded **cited** answer, the verdict pills, and an injection warning. |
| **Chunker** (`chunking.py`) | Split documents into meaningful `Chunk`s (fixed+overlap, heading-aware, semantic, contextual). **Deterministic**; a documented boundary guard so a *rule and its condition* are not silently split (§5/§14). |
| **Embedder** (`embedding.py`: `OllamaEmbedder` real, `MockEmbedder` offline double) | Map text → a fixed-dim, **L2-normalized** vector `v ∈ ℝᵈ`. **Ollama `nomic-embed-text`** for the real path; the **deterministic `MockEmbedder`** (hashed BoW, O-1) is the offline double so vector search is testable without a model. |
| **VectorStore** (`retrieval.py`) | In-memory dense index over `ScoredChunk`; `search(q_vec, k)` → top-k by **cosine** (deterministic, documented tie-break). Also hosts the **BM25 lexical** channel for hybrid mode. |
| **Retriever / Hybrid** (`retrieval.py`) | Combine the dense and lexical channels: `score = α·s_sem + (1−α)·s_lex` (§8) over normalized per-channel scores; ranked result list. Deterministic (mock embedder). |
| **QueryExpander / Multi-Query** (`expand.py`: `MockQueryExpander` default, `LLMQueryExpander` optional) | Expand a query to `{q₁,…,qₙ}` and retrieve-per-expansion → **union + dedupe** (§10/§11). Deterministic mock by default. |
| **Reranker** (`rerank.py`: `MockReranker` default, `LLMReranker` optional) | Take the fast top-N candidates and produce a more precise top-k (§9); **MockReranker** is a deterministic coverage/overlap heuristic. |
| **Contextualizer** (`context.py`) | At *index time*, prepend document/section context to each chunk's *embedding text* (§12) while preserving the original chunk text for display; pure. |
| **ContextBuilder** (`context.py`) | Turn the selected, contextualized docs into a token-bounded, deduped, source-labeled `Context` (the text the LLM sees). Pure. |
| **Citer** (`citation.py`) | Enforce the **grounding gate** — every cited `source`/`chunk_id` ∈ retrieved context (§13); produce a structured claim→source→chunk citation set; detect/flag an **injection** payload in retrieved evidence (§18). |
| **LLM** (`model.py`: `OllamaLLM` real, `MockLLM` offline double) | Given system + context + question, produce a grounded, structured **cited** answer `{answer, confidence, citations, status}`. **Never** touches the CLI/GUI. |
| **Judge** (`judgment.py`: `OllamaJudge` real, `MockJudge` offline double) | Classify a verdict `{correct, supported, complete, unsupported_claims, total_factual_claims, faithfulness, completeness, citation_quality, rationale}` (§19/§20/§21). Never touches CLI/GUI. |
| **Ollama daemon** *(external)* | Local runtime at `http://localhost:11434`: `/api/embed` (`nomic-embed-text`) and `/api/chat` (`qwen3.8:27b-mlx`). Owns the weights + CPU/GPU/NPU. Not part of this project; E-13/E-14 handle its absence. |
| **Corpus / Generator** (`corpus.py`, `gen_corpus.py`) | Load the corpus from `documents/` (each document carrying the **§7 metadata**) and generate the **ground-truth** question dataset with the §14–§19 **failure-mode tiers**. Deterministic (seeded). |
| **Eval Harness** (`pipeline.py`, `cli.py`) | Wire the stages per question, accumulate `RunMetrics` (incl. the §20 retrieval metrics + §21 generation metrics), and aggregate per tier / per capability flag (§22). |
| **Metrics** (`metrics.py`) | Compute **Precision@k, Recall@k, MRR, MAP, NDCG** (§20) and **faithfulness / completeness / citation quality** (§21) — pure, headless, testable. |
| **UI** (`ui.py`, *optional*) | One-question interactive view over the shared pipeline; never blocks on inference. |

---

