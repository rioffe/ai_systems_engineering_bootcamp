## 3. Behavior and state model

### 3.1 Index-time vs. query-time (two scopes)

Unlike ch2's per-question pipeline, ch3 has **two execution scopes**:

1. **Index time** (once per `build-index`): for every `Document` in the corpus — *chunk* (
    `Chunker`) → *contextualize* (§12, R-07) → *embed* (the **contextualized** text) → *insert*
   into the `VectorStore`; the BM25 lexical channel is also built here over the chunk text. A
   document that fails to chunk/embed is a **load/index error** (E-01), not a silent partial index.
2. **Query time** (per question, run-all): the §22 stages in §3.3 below.

This scope split is why the dense path is offline-testable: index time over the **seeded mock
corpus** + `MockEmbedder` is a pure, reproducible build (T-03); query time then exercises the
retrieval pipeline deterministically.

### 3.2 Per-case query-time state machine (`CaseState`, one question at a time)

Each question runs the §22 pipeline as a linear, single-threaded sequence of stages with a
terminal outcome. A stage failure terminates **that case** but leaves sibling cases running
(one question never poisons the next). Stages are **toggle-gated** (§22): a stage whose flag is
off is *skipped* (its node is a no-op that carries its inputs unchanged; e.g. with
`--hybrid off` the channel is pure-dense; with `--rerank off` the reranker is a passthrough).

```
   IDLE
     | start
     v
 RETRIEVING ---(hybrid? dense+lexical : dense)-i----+   ok    |
     |                                              |         |
     v ok  (top-N candidates for rerank/expand)     |         |
 EXPANDING  (off ⇒ passthrough {q}; on ⇒ {q1..qn} → retrieve-per → union+dedupe, R-06)
     | ok
     v
 RERANKING  (off ⇒ passthrough; on ⇒ MockReranker/LLMReranker over top-N → top-k, R-05)
     | ok
     v
 CONTEXTING  (dedup + token-budget assemble + label, ch2 C-03; then citation/injection gate R-08/R-21)
     | ok    ------------------------------------------------------------+
     |                                                                   |
     v                                                                   v
 GENERATING            ---- fail/timeout ----       ERROR (failure_stage ∈ {retrieval,expansion,reranking,context})
     | ok                                                     SCORED/PARTIAL (if generation/judge ran)
     v
 JUDGING   (LLM-as-judge; off ⇒ skip = retrieval-only eval)    ---- (judge fail) ----  PARTIAL (retrieval metrics intact, R-15)
     | ok
     v
 SCORED   (terminal: Answer + Verdict + RunMetrics complete)
```

| State | Meaning | Terminal? |
| ------- | ----------------------- | ----- |
| `IDLE` | Case scheduled; not yet started. | no |
| `RETRIEVING` | Hybrid/dense `retrieve(q, N)` over the vector store (and BM25 channel when `--hybrid`). | no |
| `EXPANDING` | Query expansion / multi-query (R-06), or passthrough. | no |
| `RERANKING` | Rerank top-N → top-k (R-05), or passthrough. | no |
| `CONTEXTING` | Assemble the token-bounded, contextualized, source-labeled `Context`; run the **citation/injection gate** (R-08/R-21). | no |
| `GENERATING` | `LLM.generate(system, ctx, q)` → structured **cited** answer (may retry parse). | no |
| `JUDGING` | `Judge.judge(...)` → verdict (may retry parse); skipped when `--judge off`. | no |
| `SCORED` | All run stages ok: `Answer` + `Verdict` + `RunMetrics` (incl. §20 + §21 metrics). | **yes** |
| `PARTIAL` | Retrieval + generation ok but **judge failed** (E-15): retrieval + generation metrics recorded; generation fields `None`, `failure_stage="judging"`. Row still counts for retrieval metrics. | **yes** |
| `ERROR` | A stage before judging terminal-faulted: `failure_stage` names the failing stage. | **yes** |

**Transition rules:**

- Stages are **strictly ordered and toggle-gated**: a case that reaches `CONTEXTING` has a successful
    `RERANKING`; a case in `SCORED`/`PARTIAL` has cleared `RETRIEVING`. Retrieval-stage fields
    (`retrieved`, `expected`, `precision@k`, `recall@k`, `mrr`, `ndcg@k`, …) are populated for
    **every** case that cleared `RETRIEVING`, regardless of later outcome — so a rerank/generation/
   judge fault still yields a **complete retrieval diagnosis** (§21, R-15).
- A stage's parse/validation failure triggers **retry up to `max_retries`** with an **error-informed**
   prompt (the prior attempt's failure appended as a directive), then a terminal failure for that
   stage with the **first** failure reason recorded (ch2 E-03 analog); the deterministic boundary
   never fabricates.
- The whole suite settles when **every** case is terminal (`SCORED`/`PARTIAL`/`ERROR`).
    `--stop-on-error` (opt-in) aborts on the first non-terminal fault; **default is run-all**.

### 3.3 Index-time build + the retrieval → context → generation → judge data flow

```
  INDEX TIME (per build-index):
   Document(+metadata §7) ── Chunker(strategy) ── Chunk{chunk_id,text,context,meta} ── Contextualizer(§12) ─┐
        text ── Embedder(mock|ollama) ── v∈R^D ── VectorStore.insert(chunk,v) ──────────────────────────────┘
        text ── tokenize ── BM25 index (lexical channel) ── VectorStore.lexical

  QUERY TIME (per question):
   q ── Embedder ── q_vec
      |
      ├─ dense:  VectorStore.search(q_vec, N) ── s_sem (cosine)             ┐
      └─ lex:    BM25.search(q, N)        ── s_lex                          ┤  Hybrid (R-04, §8):
                                                                            └─ score = a·norm(s_sem) + (1-a)·norm(s_lex)
         → [ScoredChunk, top-N] ── QueryExpander (on: {q1..qn} → retrieve-per → union+dedupe, R-06)
         ── Reranker (top-N → top-k, R-05) ── [ScoredChunk, top-k]
         ── ContextBuilder: dedup + token-budget + labels; Context.provenance, Context.tokens ≤ budget (ch2 C-03)
         ── Citer: grounding gate (cited ids ⊆ provenance, R-08) + injection scan (R-21) + Claim→Evidence→Source (§13)
      ── LLM.generate(system, context, q) ── Answer{answer, confidence, citations[], status}        (PROBABILISTIC)
      ── Judge.judge(q, context, answer, gold) ── Verdict{correct, supported, complete, …, faithfulness, completeness, citation_quality}   (PROBABILISTIC)
      ── metrics.retrieval(G, R_k) ── {precision@k, recall@k, mrr, map, ndcg@k}        (§20)
      ── metrics.generation(verdict) ── {faithfulness, completeness, citation_quality} (§21)
      → RunMetrics(per case)  →  AggregateMetrics(per tier / per capability flag)
```

The **deterministic** stages (index, chunk, embed*mock*, vector/hybrid math, rerank*mock*, expand
*mock*, contextualize, context, citation gate, metrics) and the **probabilistic** stages (embed
*real*, generate *real*, judge *real*) are separated by the ch1 §15 / ch2 reliability boundary. The
LLM appears **only** in generate + judge by default, and the Embedder only in the *real* embed step
(R-20; enforced by the T-02 structure scan).

---

