# rag-eval

A **retrieval-augmented-generation eval harness** built as chapter §15–§21 of the
bootcamp: a small but *measurable* pipeline (`retrieve → construct → generate → judge →
metrics`) run over a grounded question dataset, plus the **eval loop** that turns it from
a demo into an engineering artifact.

The lab instantiates the chapter's thesis —

> `LLM Application = State + Retrieval + Context Construction + Model + Tools` — with
> `Evaluation` as the feedback loop (§21).

The system splits on the **deterministic boundary** (§12/§15): the retriever, the
token-budget context builder, the metric math, and the corpus generator are **pure,
offline, reproducible** (no LLM, no network); the LLM appears **exactly twice** — answer
generation and LLM-as-judge — and is replaced by deterministic `MockLLM`/`MockJudge`
doubles so the entire test suite runs offline (R-14/I-011). The **central diagnostic**
the lab makes observable (R-12): every failed case is attributed to a *stage*
(`retrieval | context | generation | judging`), so a report tells you whether *retrieval
failed to provide evidence* or *the model failed to use it* (§18).

> The authoritative description of behavior, contracts, invariants, edge cases, and
> acceptance criteria is **`SPEC.md`**. See `SPEC.md §11 Traceability` for the id mapping.

## Design at a glance

```text
 question ─► BM25 ─► [ScoredDoc] ─► build_context(budget) ─► Context
        ─► LLM.generate ─► Answer ─► Judge ─► Verdict ─► metrics → report
                ▲ deterministic, no LLM              ▲ the only two LLM uses (§3.1/R-17)
```

- **Retrieval** is deterministic lexical **BM25** (§12 "deterministic and testable"): for a
  fixed corpus + query + params it returns a byte-identical ranked list (I-002). No
  embeddings, no vector DB (a deliberate non-goal).
- **Context** is a *resource* with a token budget (§14): dedupe, rank, drop/cut the
  lowest-score docs to fit, label each `[doc_id]`. The one estimator (`est_tokens`, O-2)
  is shared by the builder and every report, so the reported tokens *are* the built tokens
  (I-005/I-006).
- **Metrics** are the §18 TP/FP/FN decomposition (precision/recall/F1, I-007 no-division
  guards), §19 answer accuracy, and §20 hallucination rate — with a **per-tier** breakdown
  (§17 easy/multi/synthesis/distractor) and the R-12 failure-stage split (§21).

## Requirements

- Python **3.12** (managed by `uv`).
- **No Ollama needed** for the default `--mock` path or the full test suite. The real local
  model `qwen3.8:27b-mlx` (served by [Ollama](https://ollama.com),
  `http://localhost:11434`) is an *opt-in, manual* path (§9.5 / K-05).

## Development setup

```bash
# optional, for the REAL generation/judge path only:
#   ollama pull qwen3.8:27b-mlx      # already present on this box (ID 5642e97495e1)

uv sync                              # creates .venv (Python 3.12) and installs deps
uv run rag-eval gen-corpus --seed 42  # generate the ~100-doc corpus + questions.json (T-01)
uv run pytest                        # the SPEC §9 suite -- FULLY OFFLINE, no Ollama (K-01/T-14)
uv run rag-eval --mock               # full pipeline offline -> report.json (<5s, K-02)
uv run rag-eval --model qwen3.8:27b-mlx   # REAL LLM+judge over the dataset (opt-in, minutes)
```

## Layout (derived from `SPEC.md` §3–§5)

```text
src/rag_eval/
  types.py      # C-01/C-04/C-07 record types (Document, ScoredDoc, Context, Question,
                #   Answer, Verdict, Usage, RunMetrics, AggregateMetrics)
  corpus.py     # C-01 load_corpus / load_questions + the seeded generator (§15/§17)
  retrieval.py  # C-02 BM25Retriever (deterministic; O-1 formula, O-1b tie-break)   [no LLM]
  context.py    # C-03 build_context + est_tokens (token budget)                     [no LLM]
  metrics.py    # C-07 retrieval_pr + aggregate (P/R/F1, accuracy, hallucination, R-12) [no LLM]
  schemas.py    # C-05 answer/verdict JSON-Schema + parse/validate/error-informed retry
  model.py      # C-05 LLM / MockLLM / OllamaLLM (+ OllamaClient via httpx)           [probabilistic]
  judgment.py   # C-06 Judge / MockJudge / OllamaJudge                                [probabilistic]
  pipeline.py   # run_case / run_dataset (state machine §3.1, failure attribution R-12)
  cli.py        # §5.1 `rag-eval` (eval / gen-corpus / show)
  app.py        # process entry point
schemas/        # answer.json, verdict.json -- the two structured-output schemas
tests/          # SPEC §9 (pure/offline, T-01..T-16); conftest.py forces Qt offscreen
```

`retrieval.py`, `context.py`, `metrics.py`, and `corpus.py` name **no** LLM/Ollama/httpx —
the structure that makes the deterministic boundary swappable (I-009/T-02, pinned by
`tests/test_imports.py`).
