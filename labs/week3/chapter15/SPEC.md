# SPECIFICATION — Minimal Coding Agent (closed-loop control, context engineering, tool use, permission gate, verification, trajectory instrumentation, + uv)

> - **Status:** v0.1 — draft for implementation review (targeting Level 3); a `spec-review`
>    pass (`SPEC_REVIEW_REPORT.md`) is expected to raise this to v0.2.
> - **Language:** Python 3.12 | `uv` | Agent harness: deterministic loop + `MockPolicy`
>   (offline double) / Ollama `qwen3.8` over `http://localhost:11434` (opt-in real) | Environments:
>   sandboxed working-tree + shell + test runner | Instrumentation: JSON trajectory log | GUI: none
>   (`MAY`).
> - **Curriculum source:** `curriculum/week3/chapter15.md` (§1 The Coding Agent as a Control System,
>   §2 The Agent Harness, §3 Context Management, §4 Tool Use, §5 Planning, §6 Execution,
>   §7 Verification, §8 Feedback and Iteration, §9 Compaction, §10 Subagents, §11 Permissions,
>   §12 The Repository as the Agent's Environment, §13 Why Tests Become Part of the Agent's
>   Reasoning System, §14 Coding Agents as Search Systems, §15 The Full Architecture, §16 What
>   Actually Determines Coding-Agent Quality, §17 Build a Minimal Coding Agent, §18 Key Takeaways).
> - **Scope of this document:** the *authoritative specification* of a **minimal coding agent**
>   (ch15 §17/§15) — the *harness* that embeds an LLM-driven policy inside a closed-loop
>   controller (observe → reason → act → verify → feedback → repeat, §1), with **context
>   management**, a **tool controller**, a **permission layer** enforced *outside* the model
>   (§11), a **verifier** that closes the loop (§7/§13), and a **trajectory instrumentation**
>   layer that turns one run into a measurable record (§17). It is written to Level 2–3:
>   behavior, interfaces, invariants, edge cases, and failure semantics are made explicit so an
>   agent (or engineer) can derive implementation **and** verification.
> - **Normative language:** `MUST`, `MUST NOT`, `SHALL`, and `SHALL NOT` are normative.
>   `SHOULD` denotes a strong recommendation; `MAY` an optional behavior.
> - **Principle:** ch15 §16 — **system architecture can amplify model capability**; two agents
>   built on the *identical* model diverge in capability by their *engineering loop* (System A
>   `LLM → patch → return` vs System B's full observe/inspect/search/verify/repair loop, §16). The
>   central conceptual transition the exercise (ch15 §17/§18.7) demands: move from *"The model
>   generated code"* to *"The system successfully navigated a software environment to a verified
>   state."* The agent is a **closed-loop controller** (`A_t ∼ π_θ(A | C_t, O_t)`, `S_{t+1} =
>   T(S_t, A_t)`, §1); the model supplies the policy, the harness supplies the control
>   machinery, the repository is the environment, and verification supplies the feedback.

---

## 0. Intent and purpose

Chapter 15's central lesson is the mechanism that makes an LLM *engineerable* as a coder:

> **A coding agent is not an LLM.** It is an LLM embedded inside a runtime that provides context,
> tools, state, permissions, execution, and verification (ch15 §18.1, §18.3). Its fundamental
> cycle is `Observe → Reason → Act → Verify → Feedback → Repeat` (§18.2). The quality of an agent
> is not a function of its model alone but of a composition:
> `Coding Agent = Model + Harness + Tools + Context + Verification + Control` (§15), or more
> completely `Q_agent = f(Q_model, Q_context, Q_tools, Q_planning, Q_verification, Q_recovery,
> Q_permissions)` (§16).

This lab specifies the §17 exercise (*Build a Minimal Coding Agent*): build a small coding
agent around a repository whose **objective is not** to produce a production autonomous
programmer but to **understand the control loop**. The agent MUST support the ten-step §17
pipeline — receive a task, inspect files, search the codebase, read relevant files, propose an
implementation, modify files, run tests, read failures, iterate, and **stop when verification
succeeds** — arranged over the minimal §17 architecture
`Task → Context builder → LLM → Tool selection → Permission check → Tool execution → Verifier
→ Feedback ↺`.

The lab instantiates ch15 §15's full architecture as **one deterministic boundary and one
probabilistic boundary**, the same reliability split used by week 1:

- **Deterministic boundary (pure, offline, reproducible, no LLM, no network):** the **control
  loop**, the **context manager** (what to include in `C_t`, §3), the **tool controller**
  (tool definitions + execution, §4/§6), the **permission layer** (§11), the **verifier
  runner** (tests/typecheck/lint, §7), the **stopping-condition logic** (§8), and the
  **trajectory logger** (§17). Offline, the *policy* itself is a deterministic
  **`MockPolicy`** (a scripted sequence of actions, or a rule-driven repair policy) so the whole
  loop can be re-run by CI without any model.
- **Probabilistic boundary (unreliable component):** the real **Ollama policy** (`qwen3.8`) that
  emits tool-call selections and edits. It is isolated behind the `Policy` interface (§4) and
  replaced by the `MockPolicy` double for the automated suite. The model-availability taxonomy
  `DEGRADED_MOCK` / `PULL_REQUIRED` / `RUN_REAL` (carried forward from week 1 eval/rag work)
  resolves a missing daemon so a *run degrading to the mock policy* is never ambiguous in the
  trajectory.

**The evaluation discipline (§8/§13).** The agent's *own* acceptance signal is the **verifier**:
tests, a type checker, a linter, a build, or a repo-specific check (§7) transform uncertain model
output into measurable feedback. Per ch15 §13, tests are not merely a final gate — they are part
of the agent's *reasoning environment*: their output is fed back into the next `observe` step and
guides subsequent actions. Per ch15 §14 the agent is a **search-and-control system**: it explores a
space of possible repository states and uses verification to *eliminate* infeasible trajectories.

**The instrumented experiment (§17/§8).** The core acceptance activity is to **intentionally
introduce a failure** — e.g. *Task: add a function that parses configuration; Experiment: inject an
incorrect implementation* — and *observe* (a) can the agent **detect** the failure, (b) can it
**diagnose the cause**, (c) can it **repair** the implementation, and (d) **how many iterations**
it required. Each run is fully instrumented (§17) over the `trajectory.json` fields
`iteration / tool_calls / tokens / files_read / files_modified / tests_executed / test_results /
errors / time_per_iteration / final_outcome`. The experiment is reproducible *because* the
`MockPolicy` (or a fixed seed) deterministically walks the detection→diagnosis→repair arc.

**Relationship to prior weeks.** This lab is the *agent-week* payoff of the reliability split
introduced in week 1: the deterministic-vs-probabilistic seam, the `MockXxx` doubles, the
model-availability taxonomy, and "verification is the bridge between probabilistic behavior and
engineering discipline" all carry forward. The verifier here subsumes week 1's evaluator in
*spirit* (a behavioral contract that the probabilistic system must satisfy, `f(x) ∈
Y_acceptable`), but operates *inside the loop* as a runtime feedback signal rather than as an
offline report. No upstream lab artifact is consumed by import: the agent is self-contained; it
operates on an arbitrary target **repository sandbox** supplied per run.

**Primary product surface:** a CLI (`agent`) with subcommands `run` (execute one task on a
target repository and emit `trajectory.json` + a human summary), `experiment` (the §17 detection/
diagnosis/repair experiment over a target repo with an injected failure, emitting `experiment.
json`), and `inspect` (load a saved `trajectory.json` offline). All durable artifacts
(`trajectory.json`, `experiment.json`) are written by one `report.py`; no subcommand prints its
own ad-hoc serialization.

---

## 1. Actors and goals

| Actor | Goals |
| ----- | ----- |
| **User** (human, single process) | Supply a coding task (task file or `--task` string) against a **target repository** (a local clone / sandbox, never the bootcamp repo itself); run the agent offline (mock policy) or against Ollama (`--real`); launch the §17 failure-injection experiment; read the instrumented trajectory and experiment report; optionally inspect a saved trajectory. (**single-principal** — no inter-principal authorization; permissions are *action-scoping*, not *user*-scoping, ch15 §11.) |
| **Policy** (`policy.py`) | The LLM-driven policy `π_θ(A | C_t, O_t)` (§1): given the current context `C_t` and observation `O_t`, select the next action `A_t` (a tool call / an edit / "stop"). Two implementations: **`MockPolicy`** (deterministic, offline — a scripted or rule-driven action sequence, the CI double) and **`OllamaPolicy`** (opt-in real, `qwen3.8`). Only `policy.py` calls the model (§11 analog of the core-import discipline, R-15). |
| **ContextManager** (`context.py`) | Compose `C_t` from the task, the trajectory-so-far, and the repository state (§3) *without* blindly passing the entire codebase (`SHOULD`-level context engineering); implement **compaction** (§9) — preserve salient state, discard irrelevant trajectory history — behind the token budget. Pure, deterministic. |
| **ToolController** (`tools.py`) | Define and dispatch the tool set (§4/§6): `list_files`, `read_file`, `search`, `edit_file`, `run_shell` (tests / typecheck / lint / build). Each tool has a fixed schema and executes inside the **target repo sandbox only**; no tool may escape the sandbox root. |
| **PermissionLayer** (`permissions.py`) | Gate *every* action **before** execution (§11): map each tool call to an authorization decision (`ALLOW` / `DENY`) from an explicitly declared policy — a static allow-list of tools/operations, a dynamic check (path in-sandbox, command prefix), and MAY a rule-based policy. **Enforced outside the model** — the policy may *request* an action; only the permission layer *permits* it (ch15 §18.10). |
| **Verifier** (`verifier.py`) | After each modification, run the repository's **verification** (§7): tests, type checker, linter, build, and MAY repo-specific / human checks. Close the loop by returning a structured verdict `VERIFIED` / `FAILED` + captured output that feeds the next `observe` (§8). The verifier is *part of the reasoning environment* (§13), not merely a final gate. |
| **ControlLoop** (`loop.py`) | The runtime harness (§2): wire `policy → permission → tool → verifier → feedback`, drive the observe/reason/act/verify/feedback state machine (§3.1/§3.2), enforce **stopping conditions** — verification succeeds, or a bounded `--max-iterations` cap is hit (§8) — and never loop forever (I-001). |
| **TrajectoryLogger** (`instrument.py`) | Record every iteration's §17 fields (`iteration`, `tool_calls`, `tokens`, `files_read`, `files_modified`, `tests_executed`, `test_results`, `errors`, `time_per_iteration`) and the `final_outcome` (§17/§14). Byte-deterministic on the mock path (I-002). |
| **Target repository / sandbox** *(per-run input)* | The **environment** `S_t` (§1): source files, config, dependencies, build artifacts, test results, git state, environment. It is *copied into* an ephemeral sandbox so the agent's edits never mutate the user's working tree or the bootcamp repo; the verifier runs *inside* the sandbox. |
| **Ollama daemon** *(external, opt-in)* | Local runtime at `http://localhost:11434`: real generation/tool-call selection. Not part of this project; the model-availability taxonomy (R-15) resolves its absence. |
