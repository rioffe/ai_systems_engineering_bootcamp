# Chapter 4 Eval Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Chapter 4 `rag-eval` harness that validates golden datasets, runs the Chapter 3 RAG pipeline through an adapter, computes deterministic evaluation vectors, emits versioned artifacts, compares regressions, and enforces CI gates.

**Architecture:** `rag_eval` is a standalone package under `labs/week1/chapter4/src`. The deterministic core (`dataset`, `schemas`, `evaluator`, `metrics`, `failure`, `report`, `compare`, `gates`) has no Chapter 3, LLM, or network imports. Only `aoe.py` imports Chapter 3 and converts its pinned pipeline results into Chapter 4 records. CLI commands are thin orchestration over validated artifacts and all serialization is centralized in `report.py`.

**Tech Stack:** Python 3.12, `uv`, `pytest`, `jsonschema`, `PyYAML`, `httpx`, `loguru`; optional PyQt5/pytest-qt for the read-only GUI.

**Spec:** `labs/week1/chapter4/SPEC.md`

## Global Constraints

- Python MUST be `>=3.12,<3.13`.
- The deterministic eval core MUST NOT import the Chapter 3 `rag` package, Ollama, or network clients.
- `aoe.py` MUST be the only Chapter 4 module importing Chapter 3 `rag`.
- The mock path MUST be offline, deterministic, and byte-identical for identical inputs.
- Every `eval.json`, compare artifact, gate artifact, dataset report, judge-check report, and pair report MUST be schema-validated when loaded.
- Every `eval.json` MUST contain literal `eval_report_version: "0.1"`.
- All CLI usage errors MUST exit `2`; dataset violations exit `3`; pull-required real-model resolution exits `4`; gates exit `0` only when every gate passes and `1` otherwise.
- Gold fields (`reference_answer`, `relevant_chunks`, `gold_facts`) MUST never be passed to `aoe.py` or the generation prompt.
- Aggregate output MUST include lexicographically sorted `by_category`; optional `by_difficulty` is emitted only when present.
- Floats MUST serialize at fixed `%.4f` precision and missing comparison metrics MUST use literal `n/m`, never numeric zero.

---

### Task 1: Scaffold package, schemas, and dataset validation

**Files:**

- Create: `labs/week1/chapter4/pyproject.toml`
- Create: `labs/week1/chapter4/src/rag_eval/__init__.py`
- Create: `labs/week1/chapter4/src/rag_eval/dataset.py`
- Create: `labs/week1/chapter4/src/rag_eval/schema.py`
- Create: `labs/week1/chapter4/schemas/dataset.json`
- Create: `labs/week1/chapter4/schemas/labels.json`
- Create: `labs/week1/chapter4/schemas/eval.json`
- Create: `labs/week1/chapter4/schemas/compare.json`
- Create: `labs/week1/chapter4/schemas/gates.json`
- Create: `labs/week1/chapter4/schemas/pair.json`
- Create: `labs/week1/chapter4/tests/test_dataset.py`
- Create: `labs/week1/chapter4/tests/test_schema.py`

**Interfaces:**

- `dataset.py` produces `CATEGORY_SET`, `EvalCase`, `Dataset`, `DatasetViolation`, `load_dataset(path, corpus_ids=None, strict=False)`, and `validate_dataset(dataset, corpus_ids=None, strict=False)`.
- `schema.py` produces `load_json(path, schema_name)`, `validate_document(document, schema_name)`, and `load_yaml(path, schema_name)`.
- `EvalCase` fields are exactly `case_id`, `question`, `reference_answer`, `relevant_chunks`, `category`, `gold_facts`, optional `difficulty`, and `source` defaulting to `golden`.
- `Dataset` contains declared stable `dataset_id` and ordered `cases`.

- [ ] **Step 1: Write failing tests** for valid five-row data, duplicate IDs, invalid category, dangling corpus chunk, `REPLACE_ME`, malformed JSON, strict-size failure, and schema validation of labels/gates/pair documents.
- [ ] **Step 2: Run `uv run pytest tests/test_dataset.py tests/test_schema.py -q`** and verify collection fails because the package does not exist.
- [ ] **Step 3: Implement dataclasses and deterministic validation.** Enumerate all violations without returning a partial accepted dataset; strict mode alone enforces the 50-row floor; preserve input case order.
- [ ] **Step 4: Implement JSON/YAML schema loading.** Resolve schema files relative to the package/project, reject malformed documents before consumers use them, and expose explicit `SchemaError`/`DatasetError` exceptions.
- [ ] **Step 5: Run the focused tests and commit.**

```bash
git add labs/week1/chapter4/pyproject.toml labs/week1/chapter4/src labs/week1/chapter4/schemas labs/week1/chapter4/tests
git commit -m "ch4: add dataset and artifact schema validation"
```

---

### Task 2: Implement deterministic metrics and stratified aggregation

**Files:**

- Create: `labs/week1/chapter4/src/rag_eval/metrics.py`
- Create: `labs/week1/chapter4/tests/test_metrics.py`
- Modify: `labs/week1/chapter4/schemas/eval.json`

**Interfaces:**

- `METRIC_KEYS` is the closed list from C-04, including `mrr_at_k`, `map`, and `ndcg_at_k`.
- `CASE_METRIC_KEYS` and `DIRECTION_MAP`-independent metric functions produce fixed numeric values or `None` for unavailable cost.
- `near_rank_percentile(values, percentile) -> float` uses `ceil(percentile / 100 * n)`.
- `case_metrics(case, result, k) -> dict[str, float | str]` computes accuracy, retrieval metrics, groundedness, completeness, hallucination rate, latency, and cost inputs.
- `aggregate_metrics(rows, categories, difficulties=None) -> dict` always emits global metrics and sorted `by_category`, and emits `by_difficulty` only when requested.

- [ ] **Step 1: Write failing tests** for P/R/MRR/MAP/NDCG, zero denominators, parse-blocked values, claim ratios, cost-per-success, near-rank P50/P95, category means, difficulty stratification, and fixed formatting.
- [ ] **Step 2: Run the focused metrics tests and verify failure.**
- [ ] **Step 3: Implement pure metric functions.** Reuse Chapter 3 retrieval math by importing no Chapter 3 module: copy the mathematically specified functions into the eval core only if the source scan confirms no forbidden import; use documented Chapter 4 zero rules (`accuracy=0`, `P/R=0`, `groundedness/completeness=1`, `hallucination=0`, cost `None` when no successes).
- [ ] **Step 4: Implement aggregation over every case, including failures.** Parse-blocked rows map to false verdict fields and zero factual claims; no row is silently dropped.
- [ ] **Step 5: Implement recursive fixed-precision normalization for artifact serialization and run tests.**
- [ ] **Step 6: Commit.**

```bash
git add labs/week1/chapter4/src/rag_eval/metrics.py labs/week1/chapter4/schemas/eval.json labs/week1/chapter4/tests/test_metrics.py
git commit -m "ch4: add deterministic evaluation vector metrics"
```

---

### Task 3: Implement failure classification and deterministic evaluator

**Files:**

- Create: `labs/week1/chapter4/src/rag_eval/failure.py`
- Create: `labs/week1/chapter4/src/rag_eval/evaluator.py`
- Create: `labs/week1/chapter4/tests/test_failure.py`
- Create: `labs/week1/chapter4/tests/test_evaluator.py`

**Interfaces:**

- `FAILURE_CLASSES = {RETRIEVAL_FAILURE, CONTEXT_FAILURE, GENERATION_FAILURE, PARSING_FAILURE, EVALUATION_FAILURE}`.
- `classify_failure(status, failure_stage, case_id, label_disagreements=None) -> str | None` follows C-08 precedence exactly.
- `DeterministicChecks.check(result) -> list[dict]` checks parsed-answer shape and citation membership before any judge use.
- `map_verdict(verdict) -> dict` maps Chapter 3 `SCORED -> PASS`, `ERROR -> FAIL`, `PARTIAL -> FAIL` while preserving `ch3_status`; parse-invalid results become `PARSE_BLOCKED`.
- `evaluate_case(case, aoe_result, labels=None) -> EvaluationRow` produces verdict, checks, classification, case metrics inputs, and full trace without re-judging.

- [ ] **Step 1: Write failing tests** for every C-08 precedence branch, omitted stage fallback, label-only evaluation failure, citation mismatch, parse blocking, Chapter 3 status mapping, and judge-not-called behavior.
- [ ] **Step 2: Run focused tests and verify failure.**
- [ ] **Step 3: Implement deterministic checks and total status mapping.** Keep the AoE verdict authoritative; judge wrappers are not introduced here.
- [ ] **Step 4: Implement classification and row assembly.** Preserve warnings and all trace fields even for exceptions and partial results.
- [ ] **Step 5: Run focused tests and commit.**

```bash
git add labs/week1/chapter4/src/rag_eval/failure.py labs/week1/chapter4/src/rag_eval/evaluator.py labs/week1/chapter4/tests/test_failure.py labs/week1/chapter4/tests/test_evaluator.py
git commit -m "ch4: add deterministic verdict checks and failure taxonomy"
```

---

### Task 4: Build the Chapter 3 AoE adapter and offline execution path

**Files:**

- Create: `labs/week1/chapter4/src/rag_eval/aoe.py`
- Create: `labs/week1/chapter4/src/rag_eval/pipeline.py`
- Create: `labs/week1/chapter4/tests/test_aoe.py`
- Create: `labs/week1/chapter4/tests/test_pipeline.py`
- Create: `labs/week1/chapter4/documents/corpus.jsonl`
- Create: `labs/week1/chapter4/tests/fixtures/golden-5.json`

**Interfaces:**

- `AoEResult` contains question, retrieved chunks, scores, raw output, parsed answer, authoritative verdict, failure stage, usage kind/tokens, latency, cost, and trace/context fields needed by C-05.
- `build_index(corpus_dir: str, index_flags: dict) -> Index` is the only adapter entry point for index-time construction.
- `run_case(case: EvalCase, index: Index, query_flags: dict) -> AoEResult` passes only `system`, `context`, and `question` to Chapter 3 generation.
- `resolve_runtime(real: bool, model: str, judge_model: str | None) -> RuntimeResolution` returns `DEGRADED_MOCK`, `PULL_REQUIRED`, or `RUN_REAL` with exact banner and exit semantics.
- `run_dataset(dataset, corpus_dir, index_flags, query_flags, labels=None) -> EvalArtifact` executes sequentially, catches per-case exceptions, and computes aggregate metrics.

- [ ] **Step 1: Write failing adapter tests** for gold isolation, index/query flag separation, deterministic mock surrogates, Chapter 3 status normalization, per-case exception continuation, and real-runtime taxonomy.
- [ ] **Step 2: Run focused tests and verify failure.**
- [ ] **Step 3: Implement adapter imports and conversion.** Import `rag` only inside `aoe.py`; convert `EvalCase` to a Chapter 3 `Question` without exposing reference fields to generation.
- [ ] **Step 4: Implement deterministic synthetic usage.** Derive token and latency surrogates only from input/output text lengths; set real cost from a price table and synthetic cost to `None`.
- [ ] **Step 5: Implement orchestration and run tests.**
- [ ] **Step 6: Commit.**

```bash
git add labs/week1/chapter4/src/rag_eval/aoe.py labs/week1/chapter4/src/rag_eval/pipeline.py labs/week1/chapter4/tests labs/week1/chapter4/documents
git commit -m "ch4: adapt chapter3 pipeline for deterministic eval runs"
```

---

### Task 5: Implement versioned report writers and artifact loaders

**Files:**

- Create: `labs/week1/chapter4/src/rag_eval/report.py`
- Create: `labs/week1/chapter4/tests/test_report.py`
- Modify: `labs/week1/chapter4/schemas/eval.json`
- Modify: `labs/week1/chapter4/schemas/compare.json`

**Interfaces:**

- `write_json_artifact(path, artifact, schema_name) -> None` validates then writes canonical JSON with sorted keys and fixed float precision.
- `load_artifact(path, schema_name, force=False) -> dict` validates on every load and enforces report version unless forced where permitted.
- `write_dataset_report`, `write_eval_artifact`, `write_compare_report`, `write_gate_report`, `write_judge_check_report`, and `write_pair_report` are the sole durable artifact writers.
- `render_compare_table(report) -> str` and `render_summary(artifact) -> str` are the corresponding human output surfaces.

- [ ] **Step 1: Write failing tests** for versioned eval output, sorted category keys, fixed float output, schema rejection, `n/m` preservation, and stdout/file coupling.
- [ ] **Step 2: Run focused tests and verify failure.**
- [ ] **Step 3: Implement canonical serialization and schema-gated loading.** Never serialize Python `None` as a misleading metric zero; use explicit `n/m` only in compare cells.
- [ ] **Step 4: Implement human renderers from the same report objects.**
- [ ] **Step 5: Run tests and commit.**

```bash
git add labs/week1/chapter4/src/rag_eval/report.py labs/week1/chapter4/schemas labs/week1/chapter4/tests/test_report.py
git commit -m "ch4: add canonical versioned report artifacts"
```

---

### Task 6: Implement directional compare and fail-closed gates

**Files:**

- Create: `labs/week1/chapter4/src/rag_eval/compare.py`
- Create: `labs/week1/chapter4/src/rag_eval/gates.py`
- Create: `labs/week1/chapter4/tests/test_compare.py`
- Create: `labs/week1/chapter4/tests/test_gates.py`
- Create: `labs/week1/chapter4/tests/fixtures/top-k-5.json`
- Create: `labs/week1/chapter4/tests/fixtures/top-k-30.json`
- Create: `labs/week1/chapter4/tests/fixtures/gates-pass.yml`
- Create: `labs/week1/chapter4/tests/fixtures/gates-fail.yml`

**Interfaces:**

- `DIRECTION_MAP` centrally declares higher-better metrics and lower-better metrics for every `METRIC_KEYS` entry.
- `compare_artifacts(baseline, current, force=False, force_rebuild=False) -> CompareReport` checks version, dataset ID, index signature, mixed usage kind, and computes directional deltas with `n/m`.
- `evaluate_gates(compare_report, config) -> GateReport` validates metric names/units/bounds, applies absolute percentage-point or relative-percent constraints, and fails closed for missing metrics.
- `gate_exit_code(report) -> int` returns `0` iff all gates pass, otherwise `1`.

- [ ] **Step 1: Write failing tests** for both delta directions, category delta preservation, version/dataset/index mismatches, mixed usage warning, missing metrics, every gate unit form, unknown metrics, multiple bounds, pass/fail exit codes, and the top-k deliberate regression.
- [ ] **Step 2: Run focused tests and verify failure.**
- [ ] **Step 3: Implement centralized direction map and compare validation.** Refuse stale index mismatches unless explicitly forced; keep dataset ID as a declared stable name.
- [ ] **Step 4: Implement strict gate schema and directional evaluation.** Reject wrong unit/metric pairings at load time, not after metric lookup.
- [ ] **Step 5: Run tests and commit.**

```bash
git add labs/week1/chapter4/src/rag_eval/compare.py labs/week1/chapter4/src/rag_eval/gates.py labs/week1/chapter4/tests
git commit -m "ch4: add regression comparison and directional CI gates"
```

---

### Task 7: Implement judge validation, pairwise evaluation, and production scaffolding

**Files:**

- Create: `labs/week1/chapter4/src/rag_eval/judge_check.py`
- Create: `labs/week1/chapter4/src/rag_eval/pair.py`
- Create: `labs/week1/chapter4/src/rag_eval/new_case.py`
- Create: `labs/week1/chapter4/tests/test_judge_check.py`
- Create: `labs/week1/chapter4/tests/test_pair.py`
- Create: `labs/week1/chapter4/tests/test_new_case.py`

**Interfaces:**

- `judge_check(eval_artifact, labels) -> JudgeCheckReport` computes field-level agreement and disagreement pairs; no labels yields `NO_LABELS` and exit `3`.
- `run_pair(config_a, config_b, dataset, corpus_dir, judge) -> PairReport` emits per-case winners in `A|B|TIE` and `win_rate_a = a_wins / comparisons`, with ties in the denominator.
- `scaffold_case(trace, case_id) -> EvalCase` copies question/trace fields and fills all human-ground-truth fields with `REPLACE_ME` without claiming validity.

- [ ] **Step 1: Write failing tests** for agreement fractions, no-label behavior, disagreement listing, pair ties, pair schema rejection, and sentinel-filled scaffold validation.
- [ ] **Step 2: Run focused tests and verify failure.**
- [ ] **Step 3: Implement judge-check as read-only artifact comparison.** Do not rewrite eval classifications or fabricate labels.
- [ ] **Step 4: Implement pair and new-case using the existing adapter/report interfaces.**
- [ ] **Step 5: Run tests and commit.**

```bash
git add labs/week1/chapter4/src/rag_eval/judge_check.py labs/week1/chapter4/src/rag_eval/pair.py labs/week1/chapter4/src/rag_eval/new_case.py labs/week1/chapter4/tests
git commit -m "ch4: add evaluator validation pairwise runs and case scaffolds"
```

---

### Task 8: Add CLI orchestration and command-level acceptance tests

**Files:**

- Create: `labs/week1/chapter4/src/rag_eval/cli.py`
- Create: `labs/week1/chapter4/src/rag_eval/__main__.py`
- Create: `labs/week1/chapter4/tests/test_cli.py`
- Modify: `labs/week1/chapter4/pyproject.toml`
- Create: `labs/week1/chapter4/README.md`

**Interfaces:**

- Console script `rag-eval = rag_eval.cli:main`.
- `main(argv=None) -> int` supports `check`, `run`, `compare`, `gates`, `judge-check`, `pair`, `new-case`, global `--self-check`, and `--verbose/--quiet`.
- `run` revalidates datasets before building an index; invalid data exits `3`; missing corpus/path or malformed config exits `2`.
- `compare` and `gates` emit artifacts through `report.py`; `gates` emits its report on both pass and fail.

- [ ] **Step 1: Write failing subprocess/runner tests** for every command, usage exit `2`, dataset exit `3`, gates `0/1`, report creation, strict mode, `--mock`, labels, and force/version behavior.
- [ ] **Step 2: Run CLI tests and verify failure.**
- [ ] **Step 3: Implement argparse command dispatch.** Keep command functions thin and route all serialization through report writers.
- [ ] **Step 4: Implement `--self-check`.** Scan Chapter 4 source files and assert only `aoe.py` imports Chapter 3, Ollama, or network modules.
- [ ] **Step 5: Add README command examples and run the full Chapter 4 test suite.**
- [ ] **Step 6: Commit.**

```bash
git add labs/week1/chapter4/src/rag_eval/cli.py labs/week1/chapter4/src/rag_eval/__main__.py labs/week1/chapter4/pyproject.toml labs/week1/chapter4/tests/test_cli.py labs/week1/chapter4/README.md
git commit -m "ch4: expose evaluation harness CLI"
```

---

### Task 9: Add optional read-only GUI and final conformance verification

**Files:**

- Create: `labs/week1/chapter4/src/rag_eval/ui.py`
- Create: `labs/week1/chapter4/tests/test_ui.py`
- Create: `labs/week1/chapter4/tests/test_source_scan.py`
- Modify: `labs/week1/chapter4/README.md`

**Interfaces:**

- `run_gui(argv=None) -> int` opens a file picker or supplied artifact and displays summary, categories, cases, traces, and comparison deltas.
- The GUI reads only schema-validated artifacts and shows inline errors for malformed files; it never imports or calls `aoe`, `pipeline`, or inference code.

- [ ] **Step 1: Write failing offscreen tests** for eval and compare artifact rendering, malformed artifact handling, and absence of inference calls.
- [ ] **Step 2: Run GUI tests; if PyQt5 is unavailable, mark the optional suite with the project’s standard skip and verify core remains runnable.**
- [ ] **Step 3: Implement the read-only GUI with a minimal Qt model/view layout.**
- [ ] **Step 4: Run source-import scan tests and repair any forbidden core imports.**
- [ ] **Step 5: Run diagnostics and the complete verification suite.**

```bash
uv run pytest -q
uv run ruff check labs/week1/chapter4
uv run python -m rag_eval --self-check
```

- [ ] **Step 6: Inspect `lens_diagnostics(mode="all")`; resolve all blocking findings.**
- [ ] **Step 7: Commit final implementation.**

```bash
git add labs/week1/chapter4
 git commit -m "ch4: add read-only report browser and conformance checks"
```

---

## Verification Matrix

- Dataset/schema: `test_dataset.py`, `test_schema.py`, `rag-eval check`.
- Metrics/stratification: `test_metrics.py`, including T-04/T-05/T-05b/T-07.
- Deterministic evaluator/failure taxonomy: `test_evaluator.py`, `test_failure.py`, including T-06b/T-10a..e.
- Adapter/gold isolation/determinism: `test_aoe.py`, `test_pipeline.py`, including T-03/T-06/T-11/T-14.
- Artifacts/report coupling: `test_report.py`, `test_schema.py`.
- Compare/gates/deliberate regression: `test_compare.py`, `test_gates.py`, fixture artifacts, including T-08/T-09/T-09i/T-09f/T-09m.
- Judge/pair/new-case: `test_judge_check.py`, `test_pair.py`, `test_new_case.py`, including T-17/T-16/T-22/T-23.
- CLI/UI/source boundary: `test_cli.py`, `test_ui.py`, `test_source_scan.py`, including T-01/T-12/T-13/T-14/T-15b.
- Final commands: `uv run pytest -q`, `uv run ruff check labs/week1/chapter4`, `uv run python -m rag_eval --self-check`, and `lens_diagnostics(mode="all")`.

## Plan Self-Review

- All Chapter 4 requirements R-01 through R-21 map to Tasks 1–9; optional surfaces R-12/R-13/R-16 are included.
- P0/P1 review resolutions are encoded: authoritative AoE verdict, total status mapping, declared dataset ID, strict dataset floor, explicit gate units, run revalidation, parse-blocked numerics, read-only judge-check, metric closure, explicit model separation, and pair schema.
- No step relies on an unspecified file or function; interfaces are declared before downstream tasks consume them.
- No task permits the deterministic core to import Chapter 3 or perform network inference.
