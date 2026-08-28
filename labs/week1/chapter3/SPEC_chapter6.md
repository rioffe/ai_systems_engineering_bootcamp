## 5. Interface specification

### 5.1 CLI — primary surface (`rag`, R-14)

```text
Usage: rag <command> [options]

Commands:
  build-index  Chunk + (contextualize +) embed + index the corpus in memory or to a pickle
   (deterministic on --mock). Emits the index object the `eval` command consumes.
  eval        Run the full §22 pipeline over a question dataset and emit a metrics report.
  gen-corpus  Generate the ~100-doc sectioned corpus + grounded questions.json (§1 R-13).
  show        Print one case's ranked->reranked->contextualized evidence + answer + verdict
   ("what world did the model see and what did it cite?", §13/§26).

Common options:
   --dataset PATH            questions.json (default: ./questions.json)
   --corpus   PATH           document directory or .jsonl (default: ./documents)
   --out      PATH           write the JSON report (default: report.json; also -h stdout)
   --k N                 final context rank / top-k (default 5; used for P/R@k, MAP, NDCG@k)
   --top-n N          rerank candidate pool N (default 20; N >= k, else E-16)
   --alpha A         hybrid blend weight on the dense channel in [0,1] (default 0.5, R-04)
   --hybrid on|off        lexical BM25 channel on by default OFF (baseline = dense only, §22)
   --rerank on|off        MockReranker/LLMReranker over top-N (default OFF)
   --llm-rerank      use LLMReranker instead of MockReranker (real, opt-in)
   --expand on|off        query expansion / multi-query (default OFF)
   --n-expand N        number of expansions incl. the original (default 3)
   --llm-expand      use LLMQueryExpander instead of MockQueryExpander
   --strategy heading|fixed   chunking strategy; heading is DEFAULT (§6), fixed for the §14 demo
   --contextual on|off         §12 contextualize chunks before embedding (default OFF)
   --chunk-size N      characters for strategy=fixed (default 800, K-03)
   --overlap N          chunk overlap window (default 200, K-03)
   --model NAME        LLM for generate + judge (default qwen3.8:27b-mlx)
   --embed-model NAME  embedding model (default nomic-embed-text)
   --judge on|off      run LLM-as-judge (default on); off = retrieval-only eval (E-10 analog)
   --mock              force the deterministic doubles (no Ollama, no network)
   --seed N            determinism seed (default 42) (R-18)
   --tiers LIST        subset of {easy,multi,chunking,distractor,conflict,recency,injection}
   --stop-on-error     abort after the first non-terminal fault (default: run all)
   --quiet             suppress per-case stderr progress
   --verbose           loguru trace of each stage + failure_stage (§E-03 analog; off by default)
```

**`build-index` is the §22 starting point and the deterministic seam.** Because indexing (chunk +
contextualize + embed on the *mock*) is a pure function (I-001a, T-03), the default CLI run *is*
the baseline, and each `+capability` toggle in §22 is a flag that is re-run on the *same* dataset,
giving a per-capability diff (R-14). The baseline flags are: `--hybrid off --rerank off
--expand off --contextual off` (a pure dense retrieval + generate + judge).

**`eval` output (R-14, R-08, R-15, §21):**

1. A **human-readable summary** to stdout: per-metric aggregates (`precision@k`, `recall@k`,
    `mrr`, `map`, `ndcg@k`, `faithfulness`, `completeness`, `citation_quality`), the
     `failure_breakdown` (`failure_stage -> count`, R-15), and a `by_capability` diff.
2. A **machine-readable JSON report** to `--out` (the `RunMetrics` rows + `AggregateMetrics`
     with `by_tier` and `by_capability`). This is the artifact that makes a change a *measurable*
     result: re-running with `--hybrid on` shows which metric moved and *why* (§21).
3. An **injection-warning banner** when any row set `injection_warning=True` (§18, E-13).

**Exit codes.** `0` = ran (even if some cases errored — errors are *recorded* rows, §3.2 run-all
default); `2` = bad usage/CLI args; `3` = corpus/questions/index load failure (E-01/E-15; a
`relevant_chunks` id absent from the built index is a load error, I-013); `4` = a *fatal* backend
failure that `--mock` cannot paper over (E-13, *only* when `--mock` is not requested). Per-case
non-terminal faults never set a failing exit code (they are results the report carries, R-15).

### 5.2 GUI — optional surface (`rag-gui`, R-16)

Reuses the **same** `chunking/embedding/retrieval/rerank/expand/context/citation/model/
judgment/metrics` modules; the only new code is a `QThread` worker + widgets. The user types one
question; the worker runs the pipeline off the Qt event-loop thread (ch1 §3.3 pattern) and posts
signals so the UI never blocks on inference:

```text
+---------------------------------------------------------------------------+
| RAG Pipeline — retrieve/ rank/ contextualize/ cite/ generate/ judge        |
+---------------------------+-----------------------------------------------+
| QUESTION + capability spins|  RANKED (top-N, scores)   | ANSWER + VERDICT   |
| [hybrid/rerank/expand/    |  [c3] 0.42 semantic | ...  | text            |
|  contextual/strategy]      |  [c8] 0.31 semantic | ...  | confidence 0.9  |
| model / alpha / k / top_n  |  [c1] 0.28 semantic | ...  | sources/cites:   |
|   [Run] [Cancel]           |            ^ reranked top-k | [c3]§4.2 ...    |
|  banner (Ollama/mode)      |     truncation badge       | verdict pills:    |
|  INJECTION! badge (E-13)   |                            | correct/supported |
|                            |     + per-stage scores     | complete/faith/   |
|                            |                            | comple/cite_qual  |
+---------------------------+-----------------------------------------------+
```

GUI controls validate like ch1 §5.2 (non-empty question; `k in [1,100]`, `k <= top_n`, `alpha in
[0,1]`, tiers >= 1; `Cancel` enables only while running). On `Run` the pipeline executes
off-thread with `QT_QPA_PLATFORM=offscreen` for CI; the panel shows the ranked->reranked
contextualized evidence *with per-stage scores*, a truncation badge when `Context.truncated`, the
cited answer, the verdict pills, and — when the `injection` tier is exercised — a prominent
**INJECTION!** badge plus the offending chunk id (§18, R-21, E-13). **One question at a time**
(R-16).

---

