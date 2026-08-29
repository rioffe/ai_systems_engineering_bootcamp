# SPECIFICATION — Eval Harness for the Chapter-3 RAG Pipeline (golden datasets, regression reports, gates, eval-driven development, + uv)

> - **Status:** v0.1 — draft for implementation review. Written one section at a time, following the
>   ch1/ch2/ch3 lab SPEC pattern; a `SPEC_REVIEW` pass (per the `spec-review` skill) is expected before
>   v0.2, exactly as ch3 did.
> - **Language:** Python 3.12 | Application-under-evaluation (AoE): ch3 `rag` lab (imported as a path
>   dependency) | Evaluators: deterministic checks + `MockJudge` (offline double) / LLM-as-judge over
>   Ollama (opt-in real) | Schema: jsonschema | Config: PyYAML | HTTP: httpx | GUI: PyQt5 (optional)
> - **Curriculum source:** `curriculum/week1/chapter4.md` (§1 Why AI Systems Need Evals, §2 The
>   Evaluation Harness, §3 Golden Datasets, §4 What Makes a Good Evaluation Dataset, §5 Deterministic
>   Tests, §6 LLM-as-Judge, §7 Human Evaluation, §8 Pairwise Evaluation, §9 Rubric-Based Evaluation,
>   §10 Accuracy, §11 Precision/Recall, §12 Groundedness, §13 Relevance, §14 Completeness,
>   §15 Hallucination Rate, §16 Tool-Call Success, §17 Latency, §18 Cost, §19 The Evaluation Vector,
>   §20 Evaluation Is a Dataset Problem, §21 Stratified Evaluation, §22 Regression Testing,
>   §23 Regression Reports, §24 Regression Gates, §25 Don't Over-Automate, §26 Evaluator Validation,
>   §27 Pairwise Model Selection, §28 Production Evaluation, §29 Evals Change Engineering, §30 Evals as
>   the Unit-Test Analog, §31 Evals as the Missing Abstraction, §32 The Chapter 4 Exercise,
>   §33 Deliberately Introduce a Regression, §34 Failure Analysis, §35 The Evaluation Matrix,
>   §36–§39 Central Lesson / Deeper Principle / Checklist / Key Takeaways). The upstream **application
>   under evaluation (AoE)** is the ch3 RAG pipeline from `labs/week1/chapter3` (its SPEC is the
>   authoritative ch3 interface reference).
> - **Scope of this document:** the *authoritative specification* of the ch4 **evaluation subsystem** —
>   the harness that turns the ch3 RAG application from a manually-inspected demo into a measurable,
>   regression-gated engineering artifact (ch4 §31, §36). It is written to Level 2–3 (structured,
>   mostly executable): behavior, interfaces, invariants, edge cases, and failure semantics are made
>   explicit so an agent (or engineer) can derive implementation **and** verification with minimal
>   inference.
> - **Normative language:** `MUST`, `MUST NOT`, `SHALL`, and `SHALL NOT` are normative. `SHOULD` denotes
>   a strong recommendation; `MAY` an optional behavior.
> - **Principle:** ch4 §31/§30 — the evaluation suite is the *bridge between probabilistic behavior and
>   engineering discipline*; an eval does not specify an exact output string, it specifies a
>   **behavioral contract** and measures whether the probabilistic system satisfies it
>   (`f(x) ∈ Y_acceptable`, §37). Requirements express *intent*; this specification *operationalizes*
>   intent into observable behavior plus the conditions under which we know it is correct.

---

## 0. Intent and purpose

Chapter 4's central lesson is the mechanism that makes ch2 (context) and ch3 (retrieval/RAG)
**engineerable** at all:

> **Eval-driven development** — the loop `Application → Evaluation → Metrics → Failure analysis →
> Application change → Evaluation` (ch4 §0). If you cannot evaluate the behavior, you cannot reliably
> improve the system (§37).

This lab specifies the §32 exercise (*The Chapter 4 Exercise*): build a **small evaluation harness**
around the ch3 RAG system, with a **golden dataset** (50–100 cases, §32/§3), a full **evaluation
vector** of metrics (§19), **stratified** breakdowns (§21), **regression reports** comparing versions
(§23), **regression gates** suitable for CI (§24), **failure attribution** into the §34 taxonomy, and a
validated **evaluator** (§26). The six §32 experiments (chunk size, reranking off, $k$, query
expansion, LLM change, context ordering) plus the §33 deliberate regression (`top_k` 5 → 30) are the
acceptance criteria of this spec — *run them through the harness, not by eye*.

The harness instantiates ch4 §2's architecture (dataset → application → outputs → evaluator → metrics
→ regression report) around **one deterministic boundary and one probabilistic boundary**, the same
reliability split as ch1/ch2/ch3:

- **Deterministic boundary (pure, offline, reproducible, no LLM, no network):** the **dataset
  loader/validator**, the **pipeline driver** (which merely wires the AoE), the **evaluator's
  deterministic checks**, the **metric math** (P@k / R@k reuse of ch3 `metrics.py`, plus groundedness,
  completeness, hallucination rate, latency percentiles, cost-per-success), the **compare/gate logic**,
  the **failure classifier**, and the **report writers**. Offline, the AoE itself runs on ch3's mock
  doubles (`MockEmbedder` / `MockLLM` / `MockJudge` / `MockReranker` / `MockQueryExpander`), so the
  entire evaluation can be re-run by CI without any model (ch3 R-17, carried).
- **Probabilistic boundary (unreliable components):** the AoE's real Ollama generation (`qwen3.8`) and
  optionally a **real LLM-as-judge** evaluator. Both are isolated behind interfaces and replaced by
  deterministic doubles for the automated suite. ch3 R-19's model-availability taxonomy
  (`DEGRADED_MOCK` / `PULL_REQUIRED` / `RUN_REAL`, E-13) is **carried over unchanged** so that "why did
  this run degrade to mocks" is never ambiguous in an eval report (F-013).

**Evaluation hierarchy discipline (§5–§7).** The ch4 §7 hierarchy — deterministic tests → automated
metrics → LLM evaluation → human evaluation — is encoded as an *ordered evaluator pipeline*:
deterministic checks (schema-validity, citation-chunk membership, structure) run first and *before any
judge*; LLM-judge verdicts are gated on those checks; human labels (when present) are used to
**validate the judge itself** (§26), not as the primary regression groove.

**The evaluation vector (§19)** is the reporting object. Per-case and aggregate:

$$
\mathbf{Q} = (A,\ P,\ R,\ G,\ C,\ H,\ L,\ K)
$$

where $A$ = correctness (ch3 verdict `correct`), $P$ = precision@k, $R$ = recall@k, $G$ = groundedness
(faithfulness = supported claims / total factual claims, ch3 §21), $C$ = completeness (reflected
gold facts / total gold facts), $H$ = hallucination rate (unsupported claims / total claims, §15),
$L$ = latency (near-rank percentiles $P50/P90/P95/P99$, §17), and $K$ = cost per *successful* case
(§18). $T$ (tool success, §16) is a reserved slot — out of scope for the ch3 RAG's retrieval path
(single LLM call, no tool loop) but kept in the vector schema for the agent weeks.

**Deployment decision:** identical to ch3 R-19 — the real LLM path is **local Ollama** at
`http://localhost:11434`; when unavailable the harness **degrades to the mock doubles** and says so
with ch3's exact E-13 banners. The harness's *own* deterministic core is model-free (import graph
scan, T-02 analog of ch3 I-009/R-20).

**Relationship to ch3.** The AoE is consumed *by import* (path dependency on
`labs/week1/chapter3/src`), not re-implemented: ch4 exercises ch3's `build_index` / `run_case` /
`run_dataset` interface exactly as ch3's own `pipeline.py` does. This is deliberate, and it is the
entire pedagogical point of §32: **an evaluation harness wraps an existing application through a
stable interface** — you evaluate what you already built. The ch3 index-time vs query-time flag
boundary (ch3 §3.1, F-003) is carried explicitly into the experiment toggles (I-008).

**Primary product surface:** a CLI (`rag-eval`) with subcommands `check` (validate a golden dataset),
`run` (execute one evaluation and emit `eval.json` + a human report), `compare` (regression report vs
a baseline), `gates` (CI decision: exit `0` / `1`), `judge-check` (validate an evaluator against human
labels, §26), and two optional surfaces — `pair` (§27 pairwise model selection) and `new-case` (§28
production-failure → golden case scaffolding). An optional PyQt5 GUI (`rag-eval-gui`) browses run
reports — never runs inference itself.

---

## 1. Actors and goals

| Actor | Goals |
| ----- | ----- |
| **User** (human, single process) | Validate the golden dataset; run the evaluation over the AoE (mock or real); compare two runs (regression report with per-metric Δ); enforce gates in CI (exit `0`/`1`); classify failures by the §34 taxonomy; optionally browse a run report in the GUI. (**single-principal** — no inter-principal authorization, ch3 F-009 carried; `access_level` is carried but not consumed.) |
| **Dataset / Generator** (`dataset.py`) | Load the golden dataset (50–100+ `EvalCase`s), validate schema, category membership, and **reference closure** (every `relevant_chunks` id exists in the corpus); emit load errors deterministically (ch3 I-013 analog). |
| **AoE adapter** (`aoe.py`) | Drive the ch3 application through its **pinned interface** (C-02): `build_index(...)` (index-time flags), `run_case(question, index, query_time_flags)` → `AoEResult` (answer, retrieved chunks, scores, raw/parsed output, verdict, usage tokens, latency, trace). Wraps ch3; never re-implements RAG. |
| **Evaluator** (`evaluator.py`: `DeterministicChecks` first, then `MockJudge` offline / `OllamaJudge` real) | Run deterministic structure checks *before* any judge (§5); produce a per-case verdict + metrics row; classify the failure stage on non-pass (§34). |
| **Metrics** (`metrics.py`) | Reuse ch3 `metrics.py` for P@k / R@k / MRR / MAP / NDCG; add the §19 evaluation-vector math (groundedness, completeness, hallucination rate, latency percentiles, cost per success). Pure, headless, testable. |
| **Compare / Gates** (`compare.py`) | Load two `eval.json` artifacts (schema-versioned), emit the §23 regression report (per-metric directional Δ), and evaluate §24 gate thresholds as **hard directional constraints** — never a weighted composite score (§25). |
| **JudgeValidator** (`judge_check.py`) | Compare a judge's verdicts against a human-labeled sample (§26): emit agreement rate + confusion pairs — "the measurement system must itself be measured." |
| **Pairwire** (`pair.py`, *optional*) | §27 pairwise model selection: run two AoE configs over the same dataset, judge picks a winner per case, emit `WinRate`. |
| **Ollama daemon** *(external)* | Local runtime at `http://localhost:11434`: real generation (`/api/chat`) and optionally a real judge. Not part of this project; ch3's E-13 taxonomy (carried) resolves its absence. |
| **FailureClassifier** (`failure.py`) | Map every non-pass case to exactly one §34 taxonomy value (`RETRIEVAL_FAILURE` / `CONTEXT_FAILURE` / `GENERATION_FAILURE` / `PARSING_FAILURE` / `EVALUATION_FAILURE`) using the documented precedence; preserve the full trace record (§34). |
| **UI** (`ui.py`, *optional*) | Browse a saved `eval.json` report offline (per-case traces, regression table, verdict pills); never blocks on inference; offscreen-testable (ch3 R-16 analog). |

---
