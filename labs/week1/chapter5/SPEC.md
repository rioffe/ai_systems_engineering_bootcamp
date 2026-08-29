# SPECIFICATION — Bounded Research-Agent Runtime (agentic workflows, tools as APIs, authorization, budgets, traces, research-agent + uv)

> - **Status:** v0.1 — draft for implementation review (targeting Level 3).
> - **Language:** Python 3.12 | Decision policy: local Ollama `qwen3.8:27b-mlx` (deterministic
>   `MockPolicy` offline) | Tools: deterministic local-corpus `search` / `retrieve` | Schema:
>   jsonschema | Config: PyYAML | HTTP: httpx | GUI: PyQt5 (optional)
> - **Curriculum source:** `curriculum/week1/chapter5.md` (§1 The Evolution from LLM Calls to
>   Agents, §2 Stage 2: LLM + Tools, §3 Tool Calling Is an API Contract, §4 Agents vs. Workflows,
>   §5 The Agent Loop, §6 State Is the Agent's Memory, §7 Observation Is Different from Reasoning,
>   §8 Planning, §9 Reflection, §10 Loops and the Problem of Non-Termination, §11 Stopping
>   Conditions, §12 Retries, §13 Failure Recovery, §14 Delegation, §15 Permissions: The Agent Is
>   Not the User, §16 Human-in-the-Loop, §17 A Small Research Agent, §18 The Agent Runtime,
>   §19 The Agent Prompt, §20 The Agent Trace, §21 Deliberately Breaking the Agent, §22 Failure 4:
>   Tool Returns Misleading Data, §23 Failure 5: Infinite Loop, §24 Failure 6: Contradictory
>   Sources, §25 Failure 7: Permission Violation, §26 Agent Reliability Is a Systems Problem,
>   §27 Observability, §28 Deterministic Infrastructure Around a Probabilistic Core, §29 Agentic
>   Workflow vs. Autonomous Agent, §30 The Agent Design Spectrum, §31 A More Robust Agent Runtime,
>   §32 The Core Engineering Insight, §33 Engineering Principles, §34 Chapter 5 Laboratory,
>   §35 What You Should Understand by the End of Chapter 5, §36 Key Takeaways).
> - **Scope of this document:** the *authoritative specification* of the ch5 **agent runtime
>   subsystem** — the deterministic control loop (state, budgets, stopping conditions, retries,
>   authorization, validation, traces) wrapped around one probabilistic decision policy, plus the
>   §34 drill harness that deliberately breaks the agent and grades the recovery. It is written to
>   Level 2–3 (structured, mostly executable): behavior, interfaces, invariants, edge cases, and
>   failure semantics are made explicit so an agent (or engineer) can derive implementation **and**
>   verification with minimal inference.
> - **Normative language:** `MUST`, `MUST NOT`, `SHALL`, and `SHALL NOT` are normative. `SHOULD`
>   denotes a strong recommendation; `MAY` an optional behavior.
> - **Principle:** ch5 §28 — *"Put probabilistic behavior where judgment is valuable; put
>   deterministic mechanisms around it where correctness is required."* The LLM is the system's
>   **policy** ($a_t \sim \pi_\theta(a \mid s_t)$, §4/§32); every mechanism that controls external
>   side effects — schemas, permissions, budgets, retries, termination — is deterministic code,
>   and the model is never the ultimate authority over any of them.

---

## 0. Intent and purpose

Chapter 5's central question is not "how do I build an agent?" but (chapter epigraph, verbatim):

> **"How do I build a bounded, observable, recoverable control loop in which a probabilistic model
> can safely perform useful work?"**

Chapters 1–3 built a fixed pipeline (prompt → context → retrieval → cited answer → judgment);
chapter 4 made that pipeline measurable. Chapter 5 removes the predetermined execution graph: the
model now *chooses the next transition* ($a_t \sim \pi_\theta(a \mid s_t)$, $s_{t+1} = T(s_t, a_t)$,
§4), and the system becomes a **closed-loop control system** (§32). Everything ch1–ch4 taught about
deterministic boundaries now applies to a moving target: the loop itself must be bounded
(§10/§11), authorized (§15/§16), recoverable (§12/§13), and observable (§20/§27) — because the
probabilistic policy *will* eventually do something unexpected (§33 principle 10).

This lab specifies the §34 exercise (*Chapter 5 Laboratory*): build a **research agent** with
exactly two tools — `search(query)` and `retrieve(document_id)` — that accepts a research question,
searches, retrieves sources, inspects the evidence, decides whether additional searching is
necessary, and produces a final report (§17). Then **deliberately break it**: the §34 drill list
(search timeout, empty results, malformed arguments, retrieval failure, duplicate searches,
contradictory sources, low-quality sources, infinite-loop behavior, maximum-step exhaustion,
unauthorized tool call) is run *through the runtime, not by eye*, and each drill is graded on the
§34 four questions — what did the model do, what did the runtime do, what should have happened,
what instrumentation would have exposed the problem.

The runtime instantiates §31's production loop (**budgets → decide → validate → authorize →
execute-with-retry → update state**) around the same reliability split as ch1–ch4:

- **Deterministic boundary (pure, offline, reproducible, no LLM, no network):** the **runtime
  loop** and **state store** (§6), the **stopping conditions / budget enforcer** (§11), the
  **authorization policy engine** (§15), the **retry controller** with its failure-class taxonomy
  (§12), the **decision & argument validator** (§21 Failure 3, §31), the **tool router + tools**
  themselves (§3: tools are deterministic APIs over a local fixture corpus), the **trace writer**
  (§20/§27), the **loop metrics** (§33 principle 9), the **drill harness** (§34), and the **report
  writers**. Offline, the decision policy is the scripted, input-determined **`MockPolicy`**
  double (O-1), so the entire automated suite re-runs in CI without any model (ch3 R-17, carried).
- **Probabilistic boundary (unreliable component):** exactly one — the **decision policy**
  (`policy.py`): real Ollama generation (`qwen3.8:27b-mlx`, `/api/chat`) on the opt-in real path,
  the `MockPolicy` double otherwise. The policy *proposes* (`tool_call` | `final`); it never
  executes, authorizes, retries, or terminates. ch3's model-availability taxonomy
  (`DEGRADED_MOCK` / `PULL_REQUIRED` / `RUN_REAL`, ch3 E-13) is **carried over unchanged** so that
  "why did this run degrade to the mock policy" is never ambiguous in a trace (ch3 R-19 carried).

**The termination discipline (§11) is the load-bearing invariant.** The chapter's principle —
*"Never rely on the model alone to decide when the system should stop"* (§11) — is encoded as a
runtime-owned, closed set of stopping conditions (goal completion, max steps, token budget, cost
budget, time budget, repeated-state detection, tool-failure threshold) evaluated **before every
model call** (§31). The model *proposes* termination (`decision.type == "final"`); the runtime
*enforces* it (I-001). Every run, adversarial or not, terminates with exactly one recorded
`termination_reason` (I-011).

**Authorization is outside the model (§15).** Every proposed tool call passes the policy engine
*before* execution: `read/search → allowed`, `delete_file → prohibited` (§25). The §25 experiment
is a fixed acceptance drill: *"If the model can persuade the runtime to bypass authorization, the
system is architecturally broken"* — the policy engine is code, not prompt, so there is nothing to
persuade (I-002).

**Uncertainty is a first-class outcome (§13).** The agent's objective is not "always produce an
answer" but *"produce the best answer justified by the available evidence, while accurately
representing uncertainty and failure"* (§13). A run whose evidence is insufficient MUST end in a
final report that states the limitation (`status: "insufficient_evidence"`) — that is **successful
system behavior**, not a crash and never a hallucinated substitute (I-014; §21 Failure 2:
absence of evidence is not evidence of absence).

**Deployment decision:** identical to ch3/ch4 — the real policy path is **local Ollama** at
`http://localhost:11434`; when unavailable the runtime **degrades to the mock policy** and says so
with ch3's exact E-13 banners. The runtime's *own* deterministic core is model-free (import/graph
scan, T-02 analog of ch3 I-009/R-20, ch4 R-17).

**Relationship to ch3/ch4.** The ch3 RAG pipeline is a §4 **workflow** — a predetermined
transition function $s_{t+1} = F(s_t)$; ch5 promotes retrieval to an **agentic loop** where the
model selects actions, and §30's spectrum makes the tradeoff explicit. The two §34 tools are
deliberately ch3-shaped (`search` ≈ retrieval, `retrieve` ≈ document fetch) so the *only* new
variable is the loop itself. §33 principle 9 — *evaluate the loop, not just the final answer* —
is the forward bridge to ch4: this lab emits per-run **loop metrics** (tool selection, argument
correctness, unnecessary calls, recovery behavior, termination, cost, latency, §33.9/§27) as a
versioned artifact that a ch4-style harness can consume.

**Curriculum mapping:** §3 → tool contracts (C-01/C-02); §5/§31 → the runtime loop (C-05, R-01);
§6 → state model (C-04); §7/§20/§27 → trace records (C-07, R-11); §11 → stopping conditions
(C-06, R-05); §12 → retry taxonomy (C-08, R-06); §13 → uncertainty outcomes (R-08, I-014);
§15/§16/§25 → authorization (C-09, R-07); §17–§19 → research agent + prompt contract (R-02/R-03);
§21–§25/§34 → the ten drills (C-11, R-10); §28 → the boundary split (above); §33 → engineering
principles (invariants §6); §34 → laboratory acceptance (§9).

**Primary product surface:** a CLI (`research-agent`) with subcommands `run` (one bounded agent
episode over the fixture corpus), `drill` (execute one §34 failure injection and emit the
four-question drill report), and `trace` (render a saved trace human-readable), plus an optional
PyQt5 GUI (`research-agent-gui`) that browses saved traces — never runs inference itself.

---

## 1. Actors and goals

| Actor | Goals |
| ----- | ----- |
| **User** (human, single process) | Run one bounded research episode (mock or real policy); inject a §34 failure and read the drill report; render a saved trace; optionally browse traces in the GUI. (**single-principal** — no inter-principal authorization, ch3 F-009 / ch4 carried; the §15 policy engine governs *tool* authorization, not users.) |
| **Policy / LLM** (`policy.py`: `OllamaPolicy` real, `MockPolicy` offline double) | Given the serialized state + tool definitions + agent prompt (§19), emit exactly one decision per step: `{type: "tool_call", tool, arguments}` or `{type: "final", report}`. **Proposes only** — never executes tools, never self-authorizes, never terminates the loop (I-001/I-002). The `MockPolicy` is a documented, input-determined rule script (search → retrieve top hit → finalize; O-1) consuming no RNG (ch3 R-18 analog). |
| **Runtime** (`runtime.py`) | Own the §5/§31 control loop: initialize state, check stopping conditions *before every model call*, dispatch validate → authorize → execute-with-retry, update state, and guarantee termination with a recorded reason (I-001/I-011). Never itself calls the LLM API. |
| **State store** (`state.py`) | Hold the explicit §6 state $S_t = (G, H_t, O_t, M_t, P)$: goal, messages, observations, artifacts, step_count, budget counters, failure history. State lives here, **not** implicitly inside a prompt (§33 principle 3, I-010). |
| **Tool router & tools** (`tools.py`) | §3 API contracts: typed, schema-validated `search(query)` and `retrieve(document_id)` over a deterministic local fixture corpus; plus a registered-but-prohibited `delete_file(path)` existing solely to exercise §25 (C-02). Tools are deterministic: same input → same output, no network (I-003). |
| **Validator** (`validate.py`) | Reject malformed decisions/arguments *before* execution with the §21 structured error `{error, field, message}` fed back to the policy as a repair observation (R-04); validate the final report against its schema before acceptance (§31 `validate_final_answer`). |
| **Authorization / policy engine** (`authorize.py`) | §15: map every proposed `(tool, arguments)` to `allow` / `deny` from a declarative policy file (C-09); denial is final, logged, and returned as a structured observation — never retried (§12 Permission class, I-002). |
| **Budget enforcer** (`budgets.py`) | §11: evaluate the closed stopping-condition set (max steps, tokens, cost, time, repeated-state, consecutive-failures) before each step; any breach terminates the run with the matching `termination_reason` (C-06, I-001). |
| **Retry controller** (`retry.py`) | §12: classify every tool error into exactly one failure class (`TRANSIENT` / `INVALID_INPUT` / `AUTHENTICATION` / `PERMISSION` / `RATE_LIMIT` / `PERMANENT`) and apply the mapped strategy (bounded backoff-retry / repair / deny / abandon) — never blind-retry (I-006). |
| **Tracer** (`trace.py`) | §20/§27: append the full structured record per step (run id, model, prompt version, step, decision, tool, arguments, latency, result, tokens, cost, errors, retries) and the termination record; keep **action / observation / reasoning** as distinguishable typed entries (§7, I-004). |
| **Drill harness** (`drills.py`) | §34: inject one named failure (C-11 fault spec) into the tool layer, run the episode, and emit the four-question drill report (model behavior / runtime behavior / expected behavior / instrumentation) (R-10). |
| **Loop metrics** (`metrics.py`) | §33.9: compute per-run loop quality — steps used, tool-call mix, invalid-argument rate, retry counts, denial counts, unnecessary-call estimate, termination reason, latency, token/cost totals (R-11). Pure, headless, testable. |
| **Ollama daemon** *(external)* | Local runtime at `http://localhost:11434`: real policy generation (`/api/chat`, `qwen3.8:27b-mlx`). Not part of this project; ch3's E-13 taxonomy (carried) resolves its absence. |
| **UI** (`ui.py`, *optional*) | Browse a saved `trace.json` / `drill_report.json` offline (step timeline, decision/observation panes, termination banner); never blocks on inference; offscreen-testable (ch3 R-16 analog). |

---

## 2. Requirements (intent, high level)

| ID | Statement |
| -- | --------- |
| **R-01** | The system shall execute the §5/§31 **agent control loop** — `initialize_state → [evaluate stopping conditions → policy decision → validate → authorize → execute-with-retry → update_state]* → validate final report → terminate` — where the **policy proposes and the runtime disposes**: the loop drives the policy, never vice versa. The runtime SHALL evaluate every stopping condition **before each model call** (§31), so a policy that never produces `final` still terminates (I-001). |
| **R-02** | The **research agent** (§17/§34) SHALL expose exactly two operational tools — `search(query)` and `retrieve(document_id)` (C-01/C-02) — accept a research question, and produce a final report. A third tool, `delete_file(path)`, SHALL be **registered but prohibited** (C-09), existing solely as the §25 authorization target; it MUST NOT be executable under any prompt (I-002). |
| **R-03** | The **agent prompt** (§19) SHALL state the operational contract (may search/retrieve/analyze/report; do not invent evidence; prefer primary sources; state limitations; stop conditions). The prompt *specifies* behavior — including the step limit — but the **runtime enforces** every bound (§19: "the prompt specifies behavior, but the runtime still enforces the ten-call limit"); no behavioral guarantee SHALL rest on prompt text alone (I-001/I-002). |
| **R-04** | Every policy decision SHALL be **validated before execution** (§31 `valid_tool_call`): unknown tool, wrong argument types, or schema violation MUST be rejected with the §21 structured error observation `{"error": "invalid_arguments", "field": <name>, "message": <reason>}` fed back to the policy as a repair opportunity (C-03). A tool MUST never execute with invalid arguments (I-007). |
| **R-05** | The runtime SHALL enforce the §11 **closed stopping-condition set** — `goal_complete`, `max_steps`, `token_budget`, `cost_budget`, `time_budget`, `repeated_state`, `consecutive_tool_failures` — as a total enum (C-06). Each breach terminates the run with the matching `termination_reason`; the set is closed (no custom reasons) and every run ends with **exactly one** reason (I-011). *"The model can propose termination. The runtime should enforce it."* (§11). |
| **R-06** | **Retries** (§12) SHALL classify every tool error into exactly one failure class — `TRANSIENT` / `INVALID_INPUT` / `AUTHENTICATION` / `PERMISSION` / `RATE_LIMIT` / `PERMANENT` (C-08) — and apply the mapped strategy: `TRANSIENT` → bounded retry with deterministic backoff (≤ `max_retries`); `RATE_LIMIT` → deterministic backoff, counted against the same bound; `INVALID_INPUT` → structured repair observation (R-04), no blind re-execution; `PERMISSION` → deny, **never retried**; `AUTHENTICATION` → terminate the tool path with escalation recorded; `PERMANENT` → abandon the tool, record, let the policy choose an alternative. Blind retry of every error is a violation (§12, I-006). |
| **R-07** | **Authorization is outside the model** (§15/§16): every proposed `(tool, arguments)` pair SHALL pass the declarative policy engine (C-09) *before* execution — `search`/`retrieve` → `allow`, `delete_file` → `deny`. A denial MUST be logged in the trace, returned to the policy as a structured `permission_denied` observation, and counted in loop metrics. No prompt content, tool argument, or policy output can alter the authorization map at runtime (I-002; §25: *"If the model can persuade the runtime to bypass authorization, the system is architecturally broken."*). |
| **R-08** | **Uncertainty is a first-class outcome** (§13): the final report SHALL carry `status: "ok" | "insufficient_evidence"`. When retrieved evidence cannot support an answer — including the empty-results case (§21 Failure 2: *absence of evidence is not evidence of absence*) — the report MUST state the limitation explicitly (the §13 behavior: *"The requested information could not be verified from the available sources."*) and MUST NOT fabricate claims or citations (I-014). An `insufficient_evidence` termination is **successful system behavior** (E-03). |
| **R-09** | The **drill harness** (§34) SHALL execute the ten named failure drills of C-11 — `search_timeout`, `empty_results`, `malformed_arguments`, `retrieval_failure`, `duplicate_searches`, `contradictory_sources`, `low_quality_sources`, `infinite_loop`, `max_steps_exhaustion`, `unauthorized_tool_call` — by injecting a deterministic fault spec into the tool layer (never into the runtime itself) and emitting a `drill_report.json` answering the §34 four questions: model behavior / runtime behavior / expected behavior / instrumentation that exposed (or would expose) the problem (C-12). All ten drills MUST run fully offline on the `MockPolicy` (R-13). |
| **R-10** | **Non-termination defense** (§10/§23): the runtime SHALL detect semantic repetition — an `(tool, canonical(arguments))` pair seen `repeat_threshold` times — and terminate with `termination_reason: "repeated_state"` (C-06). A drill whose tool always yields nothing useful (§23) MUST end in `repeated_state` or `max_steps`, never in a hang (K-02). |
| **R-11** | **Observability** (§20/§27/§33.9): every run SHALL emit a versioned `trace.json` (C-07) carrying the full §27 field list — run id, question, model, model parameters, prompt version, per-step state snapshot reference, decision, tool name, arguments, tool latency, tool result, token usage, cost, errors, retries, `termination_reason`, final report — plus a **loop-metrics** row (C-10): steps used, tool-call mix, invalid-argument count, retry count, denial count, unnecessary-call estimate, latency, token/cost totals. *Evaluate the loop, not just the final answer* (§33 principle 9). |
| **R-12** | **Evidence evaluation** (§22/§24): observations SHALL carry provenance metadata (`source_id`, `quality: "primary" | "secondary" | "marketing"`, published date) separate from the model's interpretation (§7). The final report schema SHALL include a `conflicts` list: when two retrieved sources assert contradictory values for the same quantity (§24), the report MUST represent the conflict explicitly — never silently adopt the convenient value (E-08) — and MUST mark conclusions resting on `marketing`-quality sources with a `low_quality_evidence` caveat (E-09). |
| **R-13** | **Offline determinism** (ch3 R-17/R-18 carried): the *entire automated suite* runs offline via the `MockPolicy` double + fixture corpus; the mock path is **byte-identical for identical inputs** (floats at fixed `%.4f`, I-003), with **deterministic surrogates** for tokens/latency/cost derived from content lengths, explicitly labeled `usage_kind: "synthetic"` in the trace (ch4 R-14 analog). The `MockPolicy` consumes no seed/RNG — it is a pure function of `(state, tools)` (ch3 R-18 analog). The real Ollama path is opt-in/manual and best-effort. |
| **R-14** | **Model-availability taxonomy** (ch3 R-19/E-13 carried): on `--real` start the runtime resolves `DEGRADED_MOCK` (daemon unreachable → mock policy + banner, exit `0`), `PULL_REQUIRED` (model not pulled → exact `ollama pull <m>` remediation + exit `4`, never a crash), or `RUN_REAL` (pulled → real, no banner, exit `0`). Each outcome carries ch3's exact distinct banner text so a human never misreads why a mock policy ran (E-13). |
| **R-15** | An **optional PyQt5 GUI** (`research-agent-gui`, `MAY`) SHALL browse saved `trace.json` / `drill_report.json` artifacts offline — step timeline with typed action/observation/reasoning panes, budget gauges, termination banner, drill four-question view — without ever running inference (ch3 R-16 analog; offscreen-testable, T-13). |
| **R-16** | The **deterministic core** (`runtime.py`, `state.py`, `tools.py`, `validate.py`, `authorize.py`, `budgets.py`, `retry.py`, `trace.py`, `drills.py`, `metrics.py`, `report.py`) is **LLM- and network-free** — asserted by an import/graph source scan (T-02, ch3 I-009/R-20 analog). Only `policy.py` MAY import the LLM client (I-012). |
| **R-17** | **Observation ≠ reasoning** (§7): trace entries SHALL be typed — `action` (the proposed call), `observation` (what the tool returned), `reasoning` (the policy's stated interpretation, when present). A tool result MUST be replayable verbatim from the trace; the policy's conclusions MUST NOT be written into observation records (I-004). |
| **R-18** | **Final-report validation** (§31 `validate_final_answer`): a `final` decision's report SHALL be schema-validated (C-03); an invalid report MUST NOT be accepted — the runtime appends a structured error observation and continues the loop (bounded by the same budgets, E-04). A run can therefore only end `ok`/`insufficient_evidence` on a *valid* report, or on a budget stop (I-011). |
| **R-19** | **Schema gate + artifact versioning** (ch3 R-19 analog): `trace.json` and `drill_report.json` SHALL each carry a literal version field (`agent_trace_version == "0.1"`, `drill_report_version == "0.1"`) and be validated against `schemas/*.json` on **every** load; malformed or version-mismatched artifacts are rejected deterministically (E-06). The `trace` subcommand and the GUI consume only validated artifacts (I-009). |
| **R-20** | **Bound everything, declaratively** (§33 principle 4): every bound — `max_steps` (default `10`, §19), `max_tokens`, `max_cost_usd`, `max_seconds`, `max_retries`, `repeat_threshold`, `max_consecutive_failures` — SHALL be settable in a `budgets.yml` config (C-06) validated on load (unknown keys are config errors, ch4 I-015 analog); documented defaults apply when no config is passed. |

---
