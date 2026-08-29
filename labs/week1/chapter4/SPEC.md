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

## 2. Requirements (intent, high level)

| ID | Statement |
| -- | --------- |
| **R-01** | The system shall execute the ch4 §2 harness pipeline — **Dataset → Application → Outputs → Evaluator → Metrics → Regression Report** — where the **Application under Evaluation (AoE)** is the ch3 RAG pipeline, reached *only* through the pinned adapter interface (C-02). The harness never re-implements retrieval/generation; it wires, measures, and compares. |
| **R-02** | The **golden dataset** (§3/§32) shall hold 50–100+ `EvalCase`s, each with `question`, `reference_answer`, `relevant_chunks` (ground-truth chunk ids), and `category`, plus ch3-carried `gold_facts` for completeness (C-01). `dataset check` MUST validate schema, category membership in the documented `CATEGORY_SET` (ch3's seven failure tiers ∪ `{adversarial, boundary, regression}`, §21/§35), and **reference closure**: every `relevant_chunks` id MUST exist in the corpus index and every required field MUST be present; violations are deterministic **load errors** (E-02, ch3 I-013 analog). |
| **R-03** | The evaluator (§5/§7 hierarchy) shall run **deterministic checks before any judge**: answer-schema validity, citation-`chunk_id` membership in the retrieved context, and any property with an exact spec (e.g. `amount >= 0`, enum membership) are checked deterministically. A case whose answer fails schema validation is attributed `PARSING_FAILURE` and is judged on that basis (I-005) — no LLM verdict needed. |
| **R-04** | The harness shall compute the §19 **evaluation vector** per case and in aggregate: correctness `A` (from the ch3 verdict `correct`), retrieval `P@k` and `R@k` (ch3 `metrics.py` reuse), groundedness `G` (faithfulness = supported claims / total factual claims, ch3 §21 formula), completeness `C` (reflected `gold_facts` / total `gold_facts`), hallucination rate `H` (unsupported claims / total claims, §15), latency `L` as percentiles $P50/P90/P95/P99$ (near-rank interpolation, §17), and cost `K` per successful case (§18 formulas: `cost_success = sum(input+output tokens × price_table) / successes`). §16 tool-success `T` is a **reserved** slot (retrieval pipeline has no tool loop in ch3 — kept for the agent weeks). |
| **R-05** | **Stratification** (§21/§35): the aggregate report MUST include a `by_category` breakdown over the dataset's declared category set, plus an optional `by_difficulty` breakdown when the dataset carries difficulty metadata. A global-only aggregate is a **report violation** (I-012). |
| **R-06** | **Regression report** (§23): `compare` reads a baseline `eval.json` and a current `eval.json` (both schema-versioned, R-21) and emits a per-metric Δ table with a documented direction map (I-004: correctness/groundedness/completeness/P/R are higher-better; hallucination rate/latency percentiles/cost are lower-better). Cells lacking the metric on either side render as the explicit marker `n/m` (E-07), not a misleading zero. |
| **R-07** | **Regression gates** (§24): `gates` evaluates a YAML threshold config (C-07) as **hard directional constraints** — e.g. `accuracy_drop <= 1%`, `hallucination_increase <= 0.5%`, `p95_latency_increase <= 20%` — and returns **exit `0`** (pass) or **exit `1`** (at least one gate fails). A missing metric key on either side **fails closed** with an explicit message (E-11). Per §25, gates are directional constraints and MUST NOT collapse into a weighted composite score. |
| **R-08** | The six §32 experiments SHALL be expressible as flag mappings onto the ch3 CLI surface, honoring the ch3 **index-time vs query-time** rebuild boundary (ch3 §3.1, F-003): (1) chunk size — index-time, forces `build_index` before eval; (2) reranking off — query-time; (3) $k$ — query-time; (4) query expansion — query-time; (5) LLM change — `--model`; (6) context ordering — index-time. Comparing a baseline against a current whose experiment config implies a *stale, mismatched index* MUST be refused unless `--force-rebuild` (I-008, E-08). |
| **R-09** | The §33 **deliberate-regression exercise** (`top_k` 5 → 30) is a fixed acceptance experiment (T-09): the harness SHALL demonstrate, on the mock path, the documented pattern (recall goes up while precision, groundedness, latency, and cost move adversely) to prove local optimization can degrade the end-to-end system. |
| **R-10** | **Failure attribution** (§34): every non-pass case SHALL be assigned **exactly one** taxonomy value from the §34 set — `RETRIEVAL_FAILURE`, `CONTEXT_FAILURE`, `GENERATION_FAILURE`, `PARSING_FAILURE`, `EVALUATION_FAILURE` — mapped from ch3's `failure_stage` via the documented precedence table (C-08, I-006). The full §34 trace record (input, model/prompt version, retrieved docs, retrieval scores, context, raw output, parsed output, evaluator verdict, latency, cost) is preserved per case in `eval.json` (C-05). |
| **R-11** | **Evaluator validation** (§26): `judge-check` compares the evaluator's verdicts against a human-labeled sample file (JSON: `case_id` → human labels) and emits an agreement rate plus the disagreement pairs. If no human labels exist, the command reports `NO_LABELS` (E-09) — the harness never silently fabricates agreement. |
| **R-12** | **Pairwise evaluation** (§27, `MAY`): `pair` runs two AoE configs over the same dataset, asks the judge for a winner per case, and emits `WinRate(A) = A_wins / comparisons` with per-case verdicts (avoids absolute-score instability, §27). |
| **R-13** | **Production-loop closure** (§28, `MAY`): `new-case` scaffolds a valid `EvalCase` JSON from a stored production `AoEResult` trace (with `relevant_chunks` optionally blank-templated) so a production failure can be appended to the golden dataset after a human fills the ground truth. The command never fabricates ground truth (it scaffolds, the human completes). |
| **R-14** | **Offline determinism** (ch3 R-17/R-18 carried): the *entire automated suite* runs offline via ch3's mock doubles; the mock path is **byte-identical for identical inputs** (metrics output formatted to fixed precision, I-002). To keep that invariant while still reporting latency/cost, the mock path synthesizes **deterministic surrogates** from input/output text lengths (`usage_tokens := token estimates`, `latency_ms := deterministic content-derived`) — explicitly labeled `synthetic` in the report (C-02, E-07). The real Ollama path is opt-in/manual and best-effort. |
| **R-15** | **Model-availability taxonomy** (ch3 R-19/E-13 carried): on `--real` start the harness resolves `DEGRADED_MOCK` (daemon unreachable → mock + banner, exit `0`), `PULL_REQUIRED` (model not pulled → remediation string + exit `4`), or `RUN_REAL` (pulled → real, no banner, exit `0`). Each outcome carries ch3's exact distinct banner text so a human never misreads why a mock ran. |
| **R-16** | An **optional PyQt5 GUI** (`rag-eval-gui`, `MAY`) SHALL browse saved `eval.json` artifacts offline — run summary, `by_category` rows, per-case traces, regression Δ tables — without ever running inference (ch3 R-16 analog; offscreen-testable, T-13). |
| **R-17** | The **deterministic eval core** (`dataset.py`, `evaluator.py`, `metrics.py`, `compare.py`, `gates.py`, `failure.py`, `report.py`) is **LLM- and network-free** — asserted by an import/graph source scan (T-02, ch3 I-009/R-20 analog, ch3 T-02). |
| **R-18** | The **primary product surface** is the CLI `rag-eval` with subcommands `check`, `run`, `compare`, `gates`, `judge-check`, plus `MAY` subcommands `pair` and `new-case` (§5.1). All report I/O goes through `report.py`; no subcommand prints its own ad-hoc serialization. |
| **R-19** | **Schema gate** (ch3 R-09/R-10/I-010 carried): the `eval.json` schema and the gates-config schema are validated with jsonschema on **every** load; the evaluator's verdict record is validated before metrics are computed (C-03). A malformed artifact failing validation is rejected deterministically (E-06, E-14). |
| **R-20** | **Gold isolation** (ch3 F-001 carried): the AoE's generation path sees only `system`/`context`/`question`; the evaluator's expected values (`reference_answer`, `relevant_chunks`, `gold_facts`) never flow into generation and are consumed *only* by the evaluator/metrics stage (I-011). |
| **R-21** | **Report versioning**: every `eval.json` carries a literal `eval_report_version == "0.1"` field; `compare` and `gates` refuse mismatched versions unless `--force` (E-06). The single literal string is the compatibility surface. |

---
