# Chapter 5 Research-Agent Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the bounded `research-agent` runtime specified by Chapter 5, including deterministic local tools, explicit state, budgets, validation, authorization, retries, traces, ten failure drills, CLI commands, and an optional read-only GUI.

**Architecture:** The `research_agent` package separates one probabilistic policy boundary (`policy.py`) from a deterministic runtime core. `runtime.py` owns the loop and stopping conditions; `tools.py`, `validate.py`, `authorize.py`, `budgets.py`, `retry.py`, `trace.py`, `metrics.py`, `drills.py`, and `report.py` contain no LLM or network imports. The policy proposes only canonical `tool_call` or `final` decisions, while all execution and termination remain runtime-owned.

**Tech Stack:** Python 3.12, `uv`, `pytest`, `ruff`, `jsonschema`, `PyYAML`, `loguru`, `httpx` for opt-in Ollama, optional PyQt5/pytest-qt.

**Spec:** `labs/week1/chapter5/SPEC.md`

## Global Constraints

- Python MUST be `>=3.12,<3.13`.
- The deterministic core MUST be LLM- and network-free; only `policy.py` MAY import the LLM client.
- Operational tools MUST be exactly `search(query)` and `retrieve(document_id)`; `delete_file(path)` is registered but always denied.
- Every tool decision MUST be validated, authorized, retried by class, traced, and reflected in explicit state before the next policy call.
- Stopping conditions MUST be evaluated before every model call and every run MUST end with exactly one closed-set termination reason.
- MockPolicy and local tools MUST be offline, deterministic, and use no RNG or wall-clock artifact data.
- Trace and drill artifacts MUST use versions `agent_trace_version == "0.1"` and `drill_report_version == "0.1"` and validate on every load.
- JSON objects MUST use sorted keys, floats MUST render to four decimal places, and artifacts MUST contain no timestamps or absolute paths.
- Invalid decisions, denied calls, tool failures, retries, budgets, final-report validation, and reasoning/action/observation distinctions MUST remain observable in the trace.
- All ten named drills MUST execute offline and be graded against the pinned expected termination/predicate table.

---

### Task 1: Scaffold package, schemas, fixtures, and configuration loaders

**Files:**

- Create: `labs/week1/chapter5/pyproject.toml`
- Create: `labs/week1/chapter5/src/research_agent/__init__.py`
- Create: `labs/week1/chapter5/src/research_agent/schema.py`
- Create: `labs/week1/chapter5/src/research_agent/config.py`
- Create: `labs/week1/chapter5/schemas/decision.json`
- Create: `labs/week1/chapter5/schemas/report.json`
- Create: `labs/week1/chapter5/schemas/trace.json`
- Create: `labs/week1/chapter5/schemas/drill_report.json`
- Create: `labs/week1/chapter5/schemas/budgets.json`
- Create: `labs/week1/chapter5/schemas/policy.json`
- Create: `labs/week1/chapter5/schemas/tool.json`
- Create: `labs/week1/chapter5/corpus/corpus.jsonl`
- Create: `labs/week1/chapter5/tests/test_schema.py`
- Create: `labs/week1/chapter5/tests/test_config.py`

**Interfaces:**

- `schema.py`: `SchemaError`, `validate_document(document, name)`, `load_json(path, name)`, `load_yaml(path, name)`.
- `config.py`: `DEFAULT_BUDGETS`, `load_budgets(path=None)`, `load_policy(path=None)`, and `ConfigError`.
- Decision schema accepts only `{"type":"tool_call","tool":...,"arguments":...}` or `{"type":"final","report":...}`.
- Report schema accepts `status` in `ok|insufficient_evidence`, string `answer`, citations, conflicts, and caveats.

- [ ] **Step 1: Write failing tests** for canonical decision/report shapes, unknown decision types, malformed schema documents, default budgets, unknown budget keys, and malformed YAML.
- [ ] **Step 2: Run `unset VIRTUAL_ENV; uv run python -m pytest tests/test_schema.py tests/test_config.py -q`** and verify collection fails because the package is absent.
- [ ] **Step 3: Implement schema-gated loaders and strict config validation.** Defaults apply only when a config file is absent; malformed files never silently fall back.
- [ ] **Step 4: Add deterministic fixture corpus with primary, secondary, marketing, and contradiction-marker records.**
- [ ] **Step 5: Run focused tests, Ruff, and commit.**

```bash
git add labs/week1/chapter5 && git commit -m "ch5: scaffold schemas configs and fixture corpus"
```

---

### Task 2: Implement explicit state, deterministic tools, and validation

**Files:**

- Create: `labs/week1/chapter5/src/research_agent/state.py`
- Create: `labs/week1/chapter5/src/research_agent/tools.py`
- Create: `labs/week1/chapter5/src/research_agent/validate.py`
- Create: `labs/week1/chapter5/tests/test_state.py`
- Create: `labs/week1/chapter5/tests/test_tools.py`
- Create: `labs/week1/chapter5/tests/test_validate.py`

**Interfaces:**

- `AgentState` fields exactly follow C-04: goal, messages, observations, artifacts, step_count, tokens_used, cost_usd, consecutive_tool_failures, seen_actions, started_monotonic.
- `canonical_json(value) -> str`, `canonical_action(tool, arguments) -> str`, and deterministic surrogate accounting implement C-04 formulas.
- `ToolSpec`, `SearchHit`, `Document`, `ToolRegistry`, `build_registry(corpus_dir, fault=None)`, `search(query)`, and `retrieve(document_id)` implement C-01/C-02.
- `validate_decision(decision, registry) -> list[dict]` and `validate_final_report(report, retrieved_ids, conflict_markers) -> list[dict]` return structured `{error, field, message}` errors.

- [ ] **Step 1: Write failing tests** for state serialization/hash stability, lexical search ranking/tie-breaking, retrieval provenance, unknown-document permanent errors, malformed/null arguments, final citation membership, conflict-marker coverage, and marketing caveats.
- [ ] **Step 2: Run focused tests and verify failure.**
- [ ] **Step 3: Implement state and canonical surrogate helpers.** Token usage uses `ceil(len(canonical_json(entry))/4)`; latency uses the specified SHA-256-derived value; cost uses one USD per million surrogate tokens.
- [ ] **Step 4: Implement local tools and closed registry.** `delete_file` is visible in tool definitions but has no executable implementation and is denied by authorization.
- [ ] **Step 5: Implement decision/final-report validation and run tests.**
- [ ] **Step 6: Commit.**

```bash
git add labs/week1/chapter5/src/research_agent/{state.py,tools.py,validate.py} labs/week1/chapter5/tests && git commit -m "ch5: add explicit state local tools and validation"
```

---

### Task 3: Implement authorization, retry taxonomy, and budget enforcement

**Files:**

- Create: `labs/week1/chapter5/src/research_agent/authorize.py`
- Create: `labs/week1/chapter5/src/research_agent/retry.py`
- Create: `labs/week1/chapter5/src/research_agent/budgets.py`
- Create: `labs/week1/chapter5/tests/test_authorize.py`
- Create: `labs/week1/chapter5/tests/test_retry.py`
- Create: `labs/week1/chapter5/tests/test_budgets.py`

**Interfaces:**

- `AuthorizationEngine(policy)`, `authorize(tool, arguments) -> AuthorizationDecision`, and default-deny semantics implement C-09.
- Error classes are `TransientError`, `InvalidInputError`, `AuthenticationError`, `PermissionError`, `RateLimitError`, and `PermanentError`; `classify_error(error) -> FailureClass` is total.
- `execute_with_retry(call, budgets, attempt_state) -> ToolExecution` retries only TRANSIENT/RATE_LIMIT up to `max_retries` with deterministic backoff.
- `BudgetEnforcer(budgets).check(state) -> str | None` returns one closed termination reason or `None`; repeated canonical actions are checked before max steps.

- [ ] **Step 1: Write failing tests** for allow/deny/default-deny, delete-file non-execution, total error classification, retry bounds/backoff, authentication/permanent/permission no-retry behavior, repeated-state precedence, and token/cost/time/consecutive-failure breaches.
- [ ] **Step 2: Run focused tests and verify failure.**
- [ ] **Step 3: Implement declarative authorization.** Policy text and arguments cannot alter authorization decisions.
- [ ] **Step 4: Implement total retry classification and bounded execution.** Invalid arguments become repair observations and are never executed; permission failures are never retried.
- [ ] **Step 5: Implement budget and stopping checks using monotonic runtime state only.** Mock artifact values use deterministic surrogates, not wall-clock fields.
- [ ] **Step 6: Run focused tests and commit.**

```bash
git add labs/week1/chapter5/src/research_agent/{authorize.py,retry.py,budgets.py} labs/week1/chapter5/tests && git commit -m "ch5: add authorization retries and budget enforcement"
```

---

### Task 4: Implement policy boundary and deterministic MockPolicy

**Files:**

- Create: `labs/week1/chapter5/src/research_agent/policy.py`
- Create: `labs/week1/chapter5/src/research_agent/prompt.py`
- Create: `labs/week1/chapter5/tests/test_policy.py`
- Create: `labs/week1/chapter5/tests/test_policy_source_scan.py`

**Interfaces:**

- `Policy` protocol exposes only `decide(state_view, tools) -> dict`.
- `MockPolicy(fault=None)` implements MP-1 through MP-5 and named policy overlays: `null_query`, `repeat_last_search`, `never_final`, `attempt_delete`.
- `OllamaPolicy(model, endpoint)` is opt-in and returns the canonical decision shape; availability resolution returns `DEGRADED_MOCK`, `PULL_REQUIRED`, or `RUN_REAL` with the exact banners and exit codes.
- `AGENT_PROMPT` is a fixed versioned string that states tool, evidence, uncertainty, and stop-condition behavior.

- [ ] **Step 1: Write failing tests** for the canonical tool/final sequence, fixed reasoning strings, invalid-argument repair, delete-file attempt, never-final behavior, no RNG, and real-path availability taxonomy.
- [ ] **Step 2: Run focused tests and verify failure.**
- [ ] **Step 3: Implement MockPolicy as a pure state/tools function.** It proposes actions only and never executes, authorizes, retries, or terminates.
- [ ] **Step 4: Implement the Ollama policy behind `httpx` with explicit model flags and availability resolution.**
- [ ] **Step 5: Run source-boundary tests and commit.**

```bash
git add labs/week1/chapter5/src/research_agent/{policy.py,prompt.py} labs/week1/chapter5/tests && git commit -m "ch5: add mock and ollama policy boundary"
```

---

### Task 5: Implement trace records, loop metrics, and report writers

**Files:**

- Create: `labs/week1/chapter5/src/research_agent/trace.py`
- Create: `labs/week1/chapter5/src/research_agent/metrics.py`
- Create: `labs/week1/chapter5/src/research_agent/report.py`
- Create: `labs/week1/chapter5/tests/test_trace.py`
- Create: `labs/week1/chapter5/tests/test_metrics.py`
- Create: `labs/week1/chapter5/tests/test_report.py`

**Interfaces:**

- `TraceRecorder(question, policy_id, budgets, fault_spec)`, `record_step(...)`, `record_termination(...)`, and `to_artifact() -> dict` implement C-07.
- Trace entries are typed `reasoning`, `action`, and `observation`; observations preserve tool results verbatim.
- `compute_loop_metrics(trace) -> dict` returns all C-10 keys, including repair success, retry/denial counts, unnecessary-call estimate, totals, and termination reason.
- `write_trace(path, artifact)`, `load_trace(path)`, `write_drill_report(path, report)`, `load_drill_report(path)`, and `render_trace(artifact)` provide schema-gated durable I/O.

- [ ] **Step 1: Write failing tests** for full trace fields, typed entries, deterministic run ID, replayable observations, loop metrics, zero-denominator repair success, canonical formatting, version rejection, and absence of timestamps/absolute paths.
- [ ] **Step 2: Run focused tests and verify failure.**
- [ ] **Step 3: Implement canonical trace recording and report serialization.** Use `run_id = sha256(canonical_json(question, corpus_revision, budgets, fault_spec, policy_id, prompt_version))[:12]`.
- [ ] **Step 4: Implement pure loop metrics and human rendering from the same artifact object.**
- [ ] **Step 5: Run tests and commit.**

```bash
git add labs/week1/chapter5/src/research_agent/{trace.py,metrics.py,report.py} labs/week1/chapter5/tests && git commit -m "ch5: add deterministic traces loop metrics and reports"
```

---

### Task 6: Implement the bounded runtime loop

**Files:**

- Create: `labs/week1/chapter5/src/research_agent/runtime.py`
- Create: `labs/week1/chapter5/tests/test_runtime.py`
- Create: `labs/week1/chapter5/tests/test_runtime_determinism.py`

**Interfaces:**

- `AgentRuntime(policy, tools, budgets, authorization, recorder).run(question) -> dict` is the only control loop.
- The exact order is budget check, policy decision, validation, authorization, execute-with-retry, state update.
- Final decisions pass through final-report validation; invalid final reports become structured observations and continue under the same budgets.
- Every return artifact contains one termination reason, final report or bounded-stop report, full trace, and loop metrics.

- [ ] **Step 1: Write failing tests** for a normal search/retrieve/final episode, invalid decision repair, invalid final report continuation, goal completion, every budget stop, repeated-state precedence, persistent transient failures, and policy/tool exceptions.
- [ ] **Step 2: Run focused tests and verify failure.**
- [ ] **Step 3: Implement the loop with no policy-side execution or runtime recursion.** Update `seen_actions` for validated and denied canonical tool actions; exclude final decisions.
- [ ] **Step 4: Add deterministic mock accounting and insufficient-evidence behavior.** Empty results and failed retrievals produce the exact limitation text and no fabricated citations.
- [ ] **Step 5: Run focused tests twice and compare serialized artifacts byte-for-byte.**
- [ ] **Step 6: Commit.**

```bash
git add labs/week1/chapter5/src/research_agent/runtime.py labs/week1/chapter5/tests && git commit -m "ch5: implement bounded agent runtime loop"
```

---

### Task 7: Implement all ten §34 drills and drill grading

**Files:**

- Create: `labs/week1/chapter5/src/research_agent/drills.py`
- Create: `labs/week1/chapter5/tests/test_drills.py`
- Create: `labs/week1/chapter5/tests/fixtures/contradiction_pair.jsonl`
- Create: `labs/week1/chapter5/tests/fixtures/marketing_heavy.jsonl`

**Interfaces:**

- `DRILLS` contains exactly the ten C-11 names and deterministic `FaultSpec` values.
- `run_drill(name, budgets=None, corpus_dir=None) -> dict` runs the genuine runtime with one fault at the tool/policy boundary.
- `grade_drill(name, trace, report) -> dict` applies the pinned expected termination and additional predicates, returning `pass: bool`.
- Drill text fields are fixed templates with only documented trace-value interpolation.

- [ ] **Step 1: Write failing tests** that execute all ten drills, assert schema-valid drill reports, verify each expected termination/predicate, and verify an intentionally wrong expectation fails honestly.
- [ ] **Step 2: Run focused tests and verify failure.**
- [ ] **Step 3: Implement fault agendas without RNG or runtime modifications.** Include timeout recovery, empty evidence, malformed repair, retrieval failure, duplicates, contradictions, marketing quality, infinite loops, max steps, and authorization denial.
- [ ] **Step 4: Implement fixed four-question reports and grading.**
- [ ] **Step 5: Run all drill tests and commit.**

```bash
git add labs/week1/chapter5/src/research_agent/drills.py labs/week1/chapter5/tests && git commit -m "ch5: add ten deterministic failure drills"
```

---

### Task 8: Implement CLI, optional GUI, and acceptance fixtures

**Files:**

- Create: `labs/week1/chapter5/src/research_agent/cli.py`
- Create: `labs/week1/chapter5/src/research_agent/__main__.py`
- Create: `labs/week1/chapter5/src/research_agent/ui.py`
- Create: `labs/week1/chapter5/tests/test_cli.py`
- Create: `labs/week1/chapter5/tests/test_ui.py`
- Create: `labs/week1/chapter5/tests/test_source_scan.py`
- Create: `labs/week1/chapter5/README.md`

**Interfaces:**

- Console scripts: `research-agent = research_agent.cli:main` and `research-agent-gui = research_agent.ui:run_gui`.
- `run --question <text> [--mock|--real] [--budgets budgets.yml] [--corpus dir] --out trace.json` returns the specified exit codes.
- `drill --name <name> [--budgets budgets.yml] --out drill_report.json` is mock-only and grades the drill.
- `trace <trace.json>` schema-loads and renders without rerunning anything.
- `--self-check` scans the deterministic core and permits LLM imports only in `policy.py`.

- [ ] **Step 1: Write failing command tests** for run/drill/trace, missing flags, bad paths/configs, unknown drills, self-check, report creation, and GUI artifact loading.
- [ ] **Step 2: Run focused tests and verify failure.**
- [ ] **Step 3: Implement thin argparse dispatch and centralized report I/O.** Usage/config errors exit `2`, corpus violations exit `3`, PULL_REQUIRED exits `4`, and drill failures exit `1`.
- [ ] **Step 4: Implement the read-only GUI with inline schema errors and no runtime/policy imports.**
- [ ] **Step 5: Add README usage, drill table, artifacts, and verification commands.**
- [ ] **Step 6: Run the full suite and commit.**

```bash
git add labs/week1/chapter5 && git commit -m "ch5: expose research-agent CLI GUI and acceptance suite"
```

---

## Final Verification

Run from `labs/week1/chapter5`:

```bash
unset VIRTUAL_ENV
uv sync --extra dev
uv run python -m pytest tests -q
uv run ruff check src tests
uv run research-agent --self-check
```

Then run the Chapter 4 and Chapter 3 regression suites from their respective directories. Confirm
that all ten drills pass, two identical mock runs produce byte-identical traces, and
`lens_diagnostics(mode="all", paths=["labs/week1/chapter5"])` reports no blocking findings.

## Plan Self-Review

- R-01 through R-20 map to Tasks 1–8 and the final verification block.
- The three review HIGH findings are pinned in the task interfaces: exact decision discriminator,
  exact surrogate formulas, and exact per-drill grading expectations.
- The deterministic/probabilistic boundary is explicit in every task; only `policy.py` may import
  Ollama/httpx, while `tools.py` remains local and deterministic.
- No task depends on an undefined downstream interface; state, tools, validation, budgets, policy,
  traces, runtime, drills, and CLI are introduced in dependency order.
