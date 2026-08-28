# SPECIFICATION — RAG Pipeline System (dense + hybrid retrieval, rerank, contextual, citations, + uv)

> - **Status:** v0.1 — draft for implementation
> - **Language:** Python 3.12 | Retrieval: in-memory dense + (BM25) hybrid | Embeddings: Ollama `nomic-embed-text` (deterministic `MockEmbedder` offline) | GUI: PyQt5
(optional) | HTTP: httpx | Schema: jsonschema | LLM: local Ollama `qwen3.8:27b-mlx`
> - **Curriculum source:** `curriculum/week1/chapter3.md` (§1 Why RAG Exists, §2 RAG as a
>   Two-Stage System, §3 Embeddings, §4 Semantic Search, §5–§6 Chunking, §7 Metadata,
>   §8 Hybrid Retrieval, §9 Reranking, §10 Query Expansion, §11 Multi-Query Retrieval,
>   §12 Contextual Retrieval, §13 Citation Generation, §14–§19 RAG Failure Modes
>   1–6, §20 Measuring Retrieval, §21 End-to-End Metrics, §22 *Build the First
>   RAG System*, §23 The Retrieval–Generation Boundary, §24 Probabilistic
>   Information System, §25 RAG vs. Traditional Search, §26 The Engineering Loop,
>   §27 Checklist, §28 Key Takeaways).
> - **Scope of this document:** the *authoritative specification* of an AI-native RAG
>   **retrieval** system. It is written to Level 2–3 (structured, mostly executable):
>   behavior, interfaces, invariants, edge cases, and failure semantics are made
>   explicit so an agent (or engineer) can derive implementation **and** verification
>   with minimal inference.
> - **Normative language:** `MUST`, `MUST NOT`, `SHALL`, and `SHALL NOT` are normative.
>   `SHOULD` denotes a strong recommendation; `MAY` an optional behavior.
> - **Principle:** requirements express *intent*; this specification *operationalizes*
>   intent into observable behavior plus the conditions under which we know it is
>   correct.

---

## 0. Intent and purpose

Chapter 3's central lesson is that **RAG is not "embeddings + a vector database"** — it
is a multi-stage **information-retrieval** pipeline feeding a probabilistic
**generation** system, in which *every stage can fail and every stage must be
measurable*:

> RAG = **Information Retrieval** + **Context Engineering** + **Probabilistic Generation** (ch3 §28)

This lab is the *measurable RAG system* of §22 (*Build the First RAG System*): a
pipeline that (1) **chunks** documents, (2) **embeds** chunks and builds an in-memory
**vector index**, (3) **retrieves** (dense semantic, optionally **hybrid** with lexical
BM25), (4) **expands/multi-queries** and **reranks** the candidates, (5) **contextualizes**
and **assembles** the bounded evidence the model sees, (6) **generates** a grounded,
**cited** answer, and (7) **evaluates** the result — retrieval quality
(Precision@k / Recall@k / MRR / MAP / NDCG) *separately* from generation quality
(faithfulness / completeness / citation quality) — with ground truth.

The pipeline instantiates ch3 §2 (the two-stage split `D' = R(q,D)` then `y ∼ P(y | q, D')`)
and ch3 §1 (§2): the retriever is a **deterministic boundary** whose job is to *select
evidence*; the generator/judge is the **one probabilistic boundary**. The sharpest
recurring claims of the chapter are operationalized:

> **Semantic similarity is not relevance** (§4, §25): two documents can embed close to the
> query while only one answers it. The system exposes *where* it failed by attributing every
> failure to a stage (§21).

The spec therefore splits the system along the ch1/ch2 reliability boundary:

- **Deterministic boundary (pure, offline, reproducible, no LLM, no network, no embed model):**
  the **chunker**, the **in-memory vector store + cosine/hybrid/rerank math**, the
  **query expander / multi-query union** (mock), the **contextualizer**, the **context
  builder / token budget**, the **citation / grounding gate**, the **metric math**
  (P/R@k, MRR, MAP, NDCG, faithfulness, completeness, citation quality), the **corpus +
  question generator** (ground truth), and the **eval harness** that wires them. All of these
  have deterministic **`MockEmbedder` / `MockReranker` / `MockQueryExpander`** doubles so
  the whole suite runs offline (ch1 §9 philosophy, carried forward from ch2).
- **Probabilistic boundary (the unreliable components):** the **embedding model** (Ollama
  `nomic-embed-text`, served at `http://localhost:11434/api/embed`) and the **LLM**
  (Ollama `qwen3.8:27b-mlx`, `/api/chat`). Both are isolated behind interfaces and replaced
  by deterministic doubles for the automated suite. The LLM appears in **generation** and
  **judging** only by default; **query expansion** and **reranking** are *opt-in* LLM roles
  that default to their deterministic mocks (R-17).

**Deployment decision (ch1 §0, "APIs vs. Local Models"; ch2 precedent):** vector
*embedding* and text *generation/judging* are both *local*, performed by the **Ollama**
runtime (`http://localhost:11434`). The app gains control over latency/privacy/availability
and pays the corresponding burden (owning both runtimes, model presence). When Ollama or
either model is unavailable the system **degrades to the mock doubles** and says so (a
CLI/GUI banner, E-13/E-14) — it never requires a network to import, build, or test.

**Primary product surface:** a **CLI eval harness** (`rag`) that, per §22, starts from a
**minimal baseline** and **adds capabilities one at a time** —

```text
Baseline (dense + chunk + context + generate + judge)
   ↓  + metadata      (§7)     filter/rank by recency, authority, document type, permissions
   ↓  + hybrid        (§8)     α·semantic + (1−α)·lexical (BM25)
   ↓  + reranking     (§9)     fast top-N  →  precise top-k
   ↓  + query-expansion (§10/§11)  q → {q₁,q₂,…,qₙ}, retrieve-and-union
   ↓  + contextual    (§12)   enrich chunks with document context *before* embedding
   ↓  + citations     (§13)   answer carries claim→source→chunk; judge checks faithfulness/completeness/citation-quality
```

Each added stage is a **CLI toggle**, and after every change the same grounded dataset is
re-run, turning each architectural change into a **measurable experiment** (§22, the core
thesis of the chapter). The CLI emits a **metrics report** (human summary + JSON) with a
**per-tier breakdown** so an operator can see, e.g., that *+hybrid* lifted Recall@5 but *+contextual*
was what removed a chunk-boundary failure (§21 "where did it fail?"). An **optional PyQt5
GUI** (`rag-gui`, mirroring ch2) asks one question, shows the *ranked → reranked →
contextualized* evidence with scores, the grounded answer with its **citations**, the
verdict, and an **injection warning** when the adversarial tier is exercised — reusing the
*same* pipeline modules.

**Relationship to chapter 2.** This lab **generalizes** ch2's retriever from *deterministic
lexical BM25 only* to a **dense + hybrid + reranked + expanded + contextual** pipeline, and
reuses ch2's scaffolding (LLM-as-judge, schema gate, in-memory corpus, per-tier breakdown,
offline mock doubles, `failure_stage` attribution). Where ch2 *deliberately scoped
dense/hybrid/rerank out* (its v0.1 non-goal), ch3 *builds them in and measures their
contribution*. The dense path here is made offline-testable by a **deterministic
`MockEmbedder`** (a documented hashed-bag-of-words vector, O-1), which is what lets the
whole pipeline be asserted without the `nomic-embed-text` model.

**Non-goals (explicit, to constrain the solution space):**

- **No external vector database.** The index is an **in-memory** pure-Python store over
   `ScoredChunk` (cosine, with `numpy` as an *optional* numerical accelerator behind the
  same interface — Q-03). A hosted/embedded vector DB (faiss/pgvector/Qdrant) is an
   extension; the `VectorStore` interface is the seam.
- **No learned/dense embedding *as a runtime dependency for the test suite.*** The *real*
   embedder is Ollama's `nomic-embed-text`; the *automated* suite drives the deterministic
   `MockEmbedder`. The suite must not require any embed model or network (R-14).
- **No conversation / multi-turn.** History is a *context* input, not a feature; each
   question is one independent inference.
- **No tool-calling loop / agentic retrieval planning.** §19 (multi-hop) is realized as
   *set retrieval* (retrieve the set of mutually relevant chunks and synthesize), **not** an
   LLM-driven search loop. An agent that *plans* multi-step searches is out of scope
   (Q-02).
- **No cross-encoder / fine-tuned reranker.** Reranking is **LLM-based** (`LLMReranker`,
   opt-in, same model) or the **deterministic `MockReranker`**; a cross-encoder is an
   extension (Q-01). The `Reranker` interface is the seam.
- **No state/memory subsystem** (as in ch2): the corpus + question set are static per run.
   The *only* cross-stage state is the retrieval trace that becomes the report row.
- The app **must not require Ollama** to import, build, or run its **test suite**: the mock
   doubles provide every capability offline. Ollama + `nomic-embed-text` +
   `qwen3.8:27b-mlx` are the *real* backends for the opt-in manual smoke (§9.5).

---

