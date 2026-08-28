## 9. Acceptance criteria, tests, and evals

All tests target **Level-3 executable** criteria. The deterministic layers
(build, chunk, embed*mock*, vector/hybrid-math, rerank*mock*, expand*mock*,
contextualize, context, citation, corpus, `MockLLM`, `MockJudge`) need **no Qt, no
Ollama, no network, no embed model**; the GUI path is offscreen; the only *real*
model calls are the **manual smoke** (§9.11). Every failure mode of §14–§19 is a
*measured* outcome, not a special-cased branch.

### 9.1 Corpus and question dataset (C-01, R-13)

| ID | Criterion |
| ------ | ------------- |
| **T-01** | `gen-corpus --n-docs 100 --n-questions 25 --seed 42` writes exactly 100 distinct `documents/NNN.txt` (each carrying the §7 metadata) and a `questions.json` of 25 questions, each with `question`, `gold_answer`, a non-empty `gold_facts`, non-empty `relevant_chunks` (ids ⊆ built index), and a `tier` ∈ the seven §C-01 tiers; **two invocations with the same seed produce byte-identical files** (R-18). |
| **T-01a** | `load_corpus` + `load_questions` accept the generated artifacts and raise on a malformed/unreadable entry (E-01), a blank/missing `gold_facts` or `relevant_chunks`, or a `relevant_chunks` id absent from the built index (E-14/I-013). |
| **T-01b** | The 25-question set has a **non-trivial per-tier distribution** — all seven tiers present — with a `distractor` question whose lexically-similar-but-irrelevant docs are *also* in the corpus, a `conflict`/`recency` pair of disagreeing policies, and an `injection` question whose adversarial chunk is *retrievable*. |

### 9.2 Retrieval, dense + hybrid, rerank, expand (deterministic — R-02/R-04/R-05/R-06/R-17)

| ID | Criterion |
| ------ | ------------- |
| **T-03** | **Index-time build (I-001a, §3.1):** `build_index(docs, ...)` over the seeded mock corpus returns a `(VectorStore, BM25Index)` whose chunk set equals the deterministic chunking of the corpus; running it twice with the same seed yields byte-identical indices (no external DB, R-02). |
| **T-04** | **Determinism + tie-break (I-002):** `VectorStore.search(q_vec, k)` is byte-identical across two builds with the **same** corpus + params; the documented tie-break (`chunk_id` ascending on equal cosine, O-1b) is respected by a crafted equal-score corpus. `MockEmbedder` (O-1, FNV-1a hashed-BoW) gives a *non-trivial* ranking (shared vocabulary ⇒ non-zero cosine) and is process-independent (not Python's `hash`). |
| **T-07** | **Hybrid blend (R-04/O-3):** with `--hybrid on`, `score = α·minmax(s_sem) + (1−α)·minmax(s_lex)` reproduces the documented per-query normalization; `α=1` ⇒ pure dense, `α=0` ⇒ pure lexical; a single-candidate query normalizes to `1.0` (degenerate E-03), never divides by zero. |
| **T-23** | **Rerank / expand determinism (I-002):** `MockReranker.rerank` (0.6·coverage + 0.4·norm-cosine) and `MockQueryExpander.multi_query` (union, max-score) are byte-identical under a fixed seed; `--rerank off`/`--expand off` are exact passthroughs equal to the retriever output. |
| **T-04b** | **Multi-doc retrieval (§19/E-15):** for a `multi`-tier question, top-k contains *all* of the ≥2 mutually-relevant chunks (recall ≈ 1); expansion *raises* the `multi`-tier recall relative to the unexpanded baseline (measured, not asserted blind). |

### 9.3 Chunking + contextual retrieval (C-03/C-07, I-013)

| ID | Criterion |
| ------ | ------------- |
| **T-21** | **Chunk-boundary demonstration (E-07/§14):** a `chunking`-tier question whose single rule + governing condition lies across a naïve `--strategy fixed --overlap 0` cut yields an *incomplete* answer (`completeness < 1.0`, `failure_stage="retrieval"` on the unguarded run); `--contextual on` and/or `--overlap > 0` **recovers both halves** and lifts `completeness`. `boundary_guard` sets `split_risk=True` where a cut nears a boundary — the *measurable* form of §14/§6. |
| **T-20** | **Contextualization (R-07/§12):** with `--contextual on`, a chunk's *embedding* text is the context-prefixed form while the *shown/cited* text is the original; a bare `The limit is $5,000.` chunk is retrieved *better* when contextualized than when bare; with `--contextual off`, `embed_text == text`. |

### 9.4 Metrics — retrieval and generation (C-11, I-001/I-007)

| ID | Criterion |
| ------ | ------------- |
| **T-05a** | **The §20 worked example (I-001):** for `G={c1,c3,c5}`, `R_5=[c1,c8,c3,c9,c5]`, `k=5`: `TP=3`, `precision@5=0.60`, `recall@5=1.0`, `MRR=1.0`, `NDCG@5 ≈ 0.88547` (DCG 1.88685 / IDCG 2.13093). |
| **T-05b** | **AP/MAP + guards (I-007):** `q1` has two relevant items, one at rank 1 and one at rank 3 ⇒ `AP=(P@1+P@3)/2 = (1 + 2/3)/2 = 0.83333`, `MRR=1.0`; `q2` has one relevant item at rank 2 ⇒ `AP=MRR=0.5`. Hence `MRR=mean(1.0,0.5)=0.75`, `MAP=mean(0.83333,0.5)=0.66667`. Empty `retrieved` ⇒ `precision=None`; all-irrelevant ⇒ `precision=0.0`, `NDCG=0.0`; no `inf`/`nan` anywhere. |
| **T-08a** | **Generation guards (R-12/I-007 over judged rows):** a verdict with `total_factual_claims=4, unsupported=1` ⇒ `faithfulness=3/4=0.75`; `gold_facts` of size 4 with 3 reflected ⇒ `completeness=3/4=0.75`; `5 citations` of which 4 relevant ⇒ `citation_quality=4/5=0.8`; a verdict with `total_factual_claims=0` ⇒ `faithfulness=0.0` (the no-division-by-zero behavior). |

### 9.5 Context + budgets (ch2 C-03 analog, I-004/I-005/I-006)

| ID | Criterion |
| ------ | ------------- |
| **T-06** | **Budget (I-004/I-006):** `build_context(scored, token_budget=N)` always yields `Context.tokens <= N`; `truncated=True` **iff** a doc was dropped. A crafted `token_budget` smaller than even the top doc forces `truncated=True` with a non-empty prompt (E-05). |
| **T-06a** | **Dedupe (E-06/I-004):** two ranked docs of identical text keep the **highest-rank** copy and set `truncated=True`; lower-rank dupes drop without error. |
| **T-06b** | **Provenance + single formula (I-005):** every id in `Context.provenance` ⊆ the included docs, and `est_tokens` is the **same** `ceil(len(s)/4)`-analog used identically by the builder and the report. |

### 9.6 LLM + Judge + Citer, offline (`MockLLM` + `MockJudge` — R-08/R-09/R-10/R-12)

| ID | Criterion |
| ------ | ------------- |
| **T-08** | **Schema gate (I-010):** the answer schema rejects an out-of-range `confidence` (e.g. `1.5`) and a missing `required` field; a malformed verdict is likewise rejected; both retry up to `max_retries` then set `status="ERROR"`. Only `jsonschema`-valid objects reach `COMPLETED`/`JUDGED`. |
| **T-08b** | **Aggregate (I-012/R-08):** over a synthetic row-set, `aggregate` yields the exact mean of `precision/recall/map/ndcg/faithfulness/completeness/citation_quality` over the **non-None** rows only; `by_tier` has one sub-aggregate per populated tier and `by_capability` one per toggled §22 stage (the *+hybrid* per-capability diff). |
| **T-08c** | **Grounding gate (I-003/R-08/I-003/E-08):** an `Answer` sourcing a `chunk_id`/`source` not in `Context.provenance` is forced `supported=False`, `grounding_violation=True`, and the foreign ids are stripped/recounted as `unsupported_claims` — enforced by the harness `Citer`, **not** trusted to the model. |
| **T-11** | **Report mirrors build (I-006):** a round-tripped `report.json` row's `context_tokens`/`truncated`/`retrieved`/`which_doc_decided` exactly mirror the `Context`/ranking actually assembled for that case. |

### 9.7 Failure attribution + edge cases (R-15, §8 E-01..E-18)

| ID | Criterion |
| ------ | ------------- |
| **T-10** | **Failure attribution (I-008/R-15):** every terminal `ERROR`/`PARTIAL` names exactly one `failure_stage`; a `PARTIAL` (judge failed after a successful generate, E-15) still carries a **complete retrieval diagnosis** (`retrieved`/`precision`/`recall`/`mrr`/`ndcg`/`ap` populated) — the §21 "retrieval-vs-generation" split is *observable in the report*. |
| **T-15** | **Ground-truth integrity (E-14/I-013):** a `questions.json` referencing a `relevant_chunks` id absent from the built index makes `load_questions` raise and the CLI exit `3` (asserted via a synthetically corrupt file) — never a silent 0-recall. |
| **T-17** | **Failure-mode tiers measured, not branch-matched (§14–§19):** `conflict` and `recency` tiers resolve to the highest-`version`/latest-`updated_at` chunk and record `which_doc_decided` (E-09/E-10/R-22); the `injection` tier sets `injection_warning=True`, records the offending `chunk_id`, and the payload never alters the system prompt or the grounded answer (E-16/R-21); `distractor` tier *measureably* lowers precision (E-08). |

### 9.8 Performance smoke (K-02/K-03)

| ID | Criterion |
| ------ | ------------- |
| **T-13** | The deterministic boundary runs the **entire default ~100-doc / 25-question dataset** with all mocks in `< 5 s` (K-02); the full suite completes in `< 90 s` on a dev box (K-01). Timing is *measured*, not asserted to a single value. |

### 9.9 Structure / architecture (ch1 T-02 analog — I-009/R-20)

| ID | Criterion |
| ------ | ------------- |
| **T-02** | **Probabilistic boundary is two components (I-009/R-20):** a source scan of `retrieval.py`, `chunking.py`, `rerank.py`, `expand.py`, `context.py`, `metrics.py`, and `corpus.py` finds **no** reference to `Ollama`, `httpx`, or any model name; `Ollama`/`httpx`/model names appear **only** in `embedding.py` (`OllamaEmbedder`), `model.py` (`OllamaLLM`), and `judgment.py` (`OllamaJudge`). |
| **T-14** | **Offline full-suite (K-01/I-011):** `uv run pytest` (default) passes with no Ollama daemon, no network, and no embed model — all cases drive `MockEmbedder`+`MockLLM`+`MockJudge`+`MockReranker`+`MockQueryExpander`. |

### 9.10 GUI offscreen (C-§5.2, I-014/E-17)

| ID | Criterion |
| ------ | ------------- |
| **T-16** | **GUI offscreen + cancel (I-014/E-17/E-13):** starting a GUI run while one is active cancels the prior; after `Cancel` zero workers are alive and the panel is in a terminal state (`failure_stage="generation"`); the `injection`-tier run shows the **INJECTION!** badge plus the offending `chunk_id` — offscreen with `QT_QPA_PLATFORM=offscreen`. |

### 9.11 Manual / real-model smoke (opt-in — not in `uv run pytest`)

- `uv run rag gen-corpus --seed 42` generates the ~100-doc sectioned corpus + `questions.json` (< 1 s, deterministic, T-01).
- `uv run rag eval --mock` runs the **full §22 pipeline offline** over the generated dataset: prints the human summary + `by_tier`/`by_capability` + `failure_breakdown` and writes `report.json` (< 5 s, K-02). A human reviews a `distractor`- and a `chunking`-tier case to confirm the precision/recovery effects are *observable* (§15/§14).
- `uv run rag eval --hybrid on` (then `--rerank on`, `--contextual on`) re-runs on the **same** dataset; the `by_capability` diff shows *which metric moved* per toggle — the operational thesis of §22/§21.
- `uv run rag eval --model qwen3.8:27b-mlx --embed-model nomic-embed-text` runs the **real** dense + hybrid pipeline over the dataset (K-05, minutes on a 27B local model); the report is compared to the `--mock` run so the human sees *which* differences are retrieval-driven vs model-driven (the core diagnostic of §21/§25). **This is the only automated path that talks to Ollama**; it is **never** in `uv run pytest` (I-011).
- **GUI smoke (offscreen + one real interactive run):** launch `uv run rag-gui`; confirm the ranked→reranked→contextualized ranking + per-stage scores + truncation badge + cited answer + verdict pills + (when the `injection` tier is hit) the INJECTION! badge render for a `--model` run *and* for the `--mock` run (ch1/§5.2 analog).

---

