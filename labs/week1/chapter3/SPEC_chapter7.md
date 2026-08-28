## 6. Invariants (must hold in every valid implementation)

| ID | Invariant | Verified by |
| ---------- | --------------------------------------------------------------------- | ------------- |
| **I-001** | **Metric math (the worked examples).** `retrieval_pr`, `mrr`, `map`, `ndcg` reproduce the §C-11 worked examples (T-05a/b): `G={c1,c3,c5}`,
`R_5=[c1,c8,c3,c9,c5]` -> `P=0.60`, `R=1.0`, `MRR=1.0`, `NDCG@5=0.88547`; AP/MAP over the `q1`/`q2` example -> `MRR=0.75`, `MAP=0.66667`. | T-05a, T-05b |
| **I-002** | **Determinism (ch3 thesis).** On the mock path with a fixed `seed`, `build_index`, `search`, `hybrid`, `rerank` (mock), `expand (mock)`, `contextualize`,
`build_context`, the metric functions, and mock answers/verdicts are **byte-identical** across two runs on the same corpus + query + params (R-18). | T-03, T-04, T-07,
T-23 |
| **I-003** | **Grounding / anti-hallucination.** Every `chunk_id`/`source` in a cited `Answer` is a subset of `Context.provenance`; the `Citer` drops any foreign id,
forces `grounding_violation=True` + `supported=False`, and the dropped ids count as `unsupported_claims`. | T-08c, E-08 |
| **I-004** | **Token budget.** `Context.tokens <= token_budget` always; `truncated=True` **iff** at least one doc was dropped to fit (E-05). | T-06 |
| **I-005** | `est_tokens(s)` is the **single** deterministic formula used identically by the context builder and the report (§C-11 `O-2`, `ceil(len(s)/4)` analog of ch2;
the reported `context_tokens` equals what was built). | T-06b |
| **I-006** | Reported `context_tokens`/`truncated`/`retrieved` exactly mirror the `Context`/ranking actually assembled for that case (report equals build). | T-11 |
| **I-007** | **No division by zero.** `precision=None` when `TP+FP=0`; `recall=None` when `TP+FN=0`; `mrr=0.0` when nothing relevant retrieved; `ndcg=None` when
`IDCG=0`; `faithfulness`/`completeness`/`citation_quality=0.0` when their denominator is 0; a no-retrieval row contributes nothing to a mean. | T-05b, T-08a, T-08 |
| **I-008** | **Failure attribution (R-15).** Every terminal `ERROR`/`PARTIAL` names exactly one `failure_stage`; retrieval-stage fields are populated for any case that
cleared `RETRIEVING`, so a later stage fault still yields a complete retrieval diagnosis. | T-10, E-15 |
| **I-009** | **Probabilistic boundary is two components.** `Ollama`/`httpx`/a model name appear **only** in `embedding.py` (`OllamaEmbedder`), `model.py` (`OllamaLLM`),
and `judgment.py` (`OllamaJudge`); `retrieval.py`, `chunking.py`, `rerank.py`, `expand.py`, `context.py`, `citation.py`, `metrics.py`, `corpus.py` name none (R-20;
source-scan). | T-02 |
| **I-010** | **Schema gate.** A case/row reaches `COMPLETED`/`JUDGED` only via a `jsonschema`-valid object (ch1 I-009); an out-of-range `confidence` or a missing
`required` field -> reject/retry/`ERROR`, never `COMPLETED`. | T-08 |
| **I-011** | No Ollama and no network are required to import the package or run the **test suite**; the suite drives
`MockEmbedder`+`MockLLM`+`MockJudge`+`MockReranker`+`MockQueryExpander` only (R-17). | T-02, T-14 |
| **I-012** | `AggregateMetrics.by_tier` holds one sub-aggregate per populated tier and `by_capability` one per toggled §22 stage; the root aggregate equals the
cross-tier combination of the same formulas; means over non-None rows only. | T-08b |
| **I-013** | **Chunk + ground-truth integrity.** No chunking strategy silently orphans a rule from its condition (the guard prefers the larger/overlap-safe unit and sets
`split_risk=True`, E-05); and every `Question.relevant_chunks` id **must exist in the built index** — an absent id is a load-time error (I-013, E-15), never a silent
0-recall. | T-21, T-15 |
| **I-014** | The GUI's `Cancel`/error path tears down the worker (no live worker survives) and leaves a terminal panel (`failure_stage="generation"` on user cancel). |
T-16 |
