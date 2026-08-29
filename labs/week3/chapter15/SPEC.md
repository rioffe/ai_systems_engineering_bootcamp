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

---

## 2. Requirements (intent, high level)

| ID | Statement |
| -- | --------- |
| **R-01** | The system executes the ch15 §17 **minimal coding-agent pipeline** in a closed loop — *receive task → inspect repository files → search the codebase → read relevant files → propose implementation → modify files → run tests → read failures → iterate → **stop when verification succeeds*** — arranged over the §17 architecture `Task → Context builder → LLM → Tool selection → Permission check → Tool execution → Verifier → Feedback ↺`. The loop is the §1/§18.2 controller `observe → reason → act → verify → feedback → repeat` (`A_t ∼ π_θ(A | C_t, O_t)`, `S_{t+1} = T(S_t, A_t)`); it terminates only on a defined **stopping condition** (R-08), never by accident. |
| **R-02** | The system is an **agent harness** (§2), not an LLM: it wires `policy → permission → tool → verifier → feedback` and owns tool definitions, tool execution, and **state management** across iterations (§2). The LLM is reached *only* through the `Policy` interface (R-15); the harness itself contains no model call. |
| **R-03** | **Context engineering** (§3/§18.4): the `ContextManager` composes `C_t` dynamically from the task, the trajectory-so-far, and observed repository state `O_t`, selecting the *relevant* slice of the repository rather than passing the entire codebase (`C_t` MUST NOT be the whole repo by default; I-005). Context composition MUST be **deterministic** for identical inputs. |
| **R-04** | **Tool use** (§4/§6): the `ToolController` dispatches a fixed, schema-pinned tool set — `list_files`, `read_file`, `search`, `edit_file`, `run_shell` (running tests / typecheck / lint / build) — each with a declared input/output contract (C-03). Tool execution extends the model into the filesystem/shell/verification *environment* (§18.5). |
| **R-05** | **Permissions enforced outside the model** (§11/§18.10): *every* tool call is gated by the `PermissionLayer` **before** execution (§3.2 act-stage) via a static allow-list (tools/operations), a dynamic check (path-in-sandbox, command-prefix), and MAY a rule-based policy; the decision is `ALLOW`/`DENY` (C-04). The policy may only *request* an action; only the permission layer *permits* it. |
| **R-06** | **Verification closes the loop** (§7/§13/§18.11): after each modification the `Verifier` runs the repository's verification — tests, type-checker, linter, build, and MAY repo-specific / human checks — and returns a structured verdict `VERIFIED`/`FAILED` plus captured output (C-05). The verifier output is a **reasoning signal** fed into the next `observe` step, not merely a final gate (§13). |
| **R-07** | **Feedback and iteration** (§8): a `FAILED` verdict is fed back as the next `O_t` and the loop continues (detection → diagnosis → repair). Per ch15 §14 the agent is a **search-and-control system**: each iteration eliminates infeasible trajectories by discarding states that fail verification. |
| **R-08** | **Stopping conditions** (§8): the loop stops when (a) the verifier returns `VERIFIED` (`final_outcome = VERIFIED`), or (b) a bounded `--max-iterations N` cap is reached (`final_outcome = BUDGET_EXHAUSTED`, a *non-zero* exit), and MAY stop on repeated identical consecutive trajectories / no-op actions (`STALLED`). The default `--max-iterations` is finite (**I-001**: no unbounded loop). |
| **R-09** | **Trajectory instrumentation** (§17/§14): every run emits `trajectory.json` recording, *per iteration*, the §17 fields `iteration`, `tool_calls`, `tokens` (consumed), `files_read`, `files_modified`, `tests_executed`, `test_results`, `errors`, `time_per_iteration`, and a top-level `final_outcome`. Emitted by `report.py` (R-16); byte-deterministic on the mock path (I-002). |
| **R-10** | **Compaction** (§9, `MAY`/default-on): for trajectories exceeding a token budget the `ContextManager` compacts — preserving salient state (task, open edits, last `VERIFIED`/`FAILED` verdict, file manifest) and discarding redundant history — so a long agent run does not blow the context window. Compaction is **state management**, not merely token trimming (§18.8). |
| **R-11** | The ch15 §17 **failure-injection experiment** is a fixed acceptance activity (T-04/T-05): *Task — add a function that parses configuration; Experiment — inject an incorrect implementation.* The run MUST demonstrate the detection → diagnosis → repair arc and report the number of iterations required; it MUST be **reproducible** on the `MockPolicy` path. |
| **R-12** | **Sandbox isolation** (§12/§16): each run operates on a *copy* of the target repository in an ephemeral sandbox root; no tool or the verifier ever mutate the user's working tree or the bootcamp repo, and no `run_shell`/`search`/`read_file`/`edit_file` may resolve a path *outside* the sandbox root (R-05, I-003). The sandbox is the agent's **environment** `S_t` (§12/§18.12). |
| **R-13** | **Offline determinism** (carried week-1 discipline): the *entire automated suite* runs offline via `MockPolicy` — a scripted or rule-driven policy — with **no network and no model**; mock-path artifacts are **byte-identical** for identical inputs (I-002). `tokens`/`time_per_iteration` on the mock path are deterministic surrogates, explicitly labeled `synthetic` in the trajectory (E-04). The real Ollama path is opt-in/manual and best-effort. |
| **R-14** | **Model-availability taxonomy** (carried): on `--real` start the agent resolves `DEGRADED_MOCK` (daemon unreachable → `MockPolicy` + banner, exit `0`), `PULL_REQUIRED` (`qwen3.8` not pulled → remediation string + exit `4`), or `RUN_REAL` (pulled → real policy, no banner, exit `0`). Each outcome carries a distinct banner so a *run that degraded to the mock policy* is never ambiguous in the trajectory. |
| **R-15** | **Policy isolation / determinism boundary** (§2/§11 analog of core-import discipline): the deterministic harness core (`control_loop.py`, `context.py`, `tools.py`, `permissions.py`, `verifier.py`, `instrument.py`, `report.py`) MUST be **LLM- and network-free**, asserted by an import/graph source scan (T-02). Only `policy.py` (the `OllamaPolicy` branch) MAY import the network/model client; `MockPolicy` does not. |
| **R-16** | The **primary product surface** is the CLI `agent` with subcommands `run`, `experiment`, `inspect` (§5.1). All durable artifacts (`trajectory.json`, `experiment.json`) are written by one `report.py`; no subcommand prints its own ad-hoc serialization. |
| **R-17** | **Schema gate** (carried): `trajectory.json` and `experiment.json` carry a literal `trajectory_version`/`experiment_version == "0.1"` field; `inspect`/`experiment` refuse a mismatched version unless `--force` (E-06). A malformed artifact failing validation is a deterministic load error (E-05). |
| **R-18** | **System-A vs System-B demonstration** (ch15 §16, `SHOULD`): the CLI MAY run a `--baseline` "System A" (`patch-only: read task → propose → write → stop`, no verify/loop) alongside the full "System B" to make §16's thesis observable — same task, same (mock) model, different loop, divergent capability — and record both trajectories. Not required for acceptance. |

---

## 3. Behavior and state model

### 3.1 Lifecycle scope

One **run** is one closed-loop task execution. Each run moves through a finite state machine whose
drive is the §1 controller; the *durable artifact* is the trajectory over that run, not the loop's
transient memory. Within one run, three nested scopes operate:

- **Per-iteration** (`OBSERVE → REASON → ACT → VERIFY → FEEDBACK`): compose `C_t`, let the `Policy`
  pick `A_t`, gate `A_t` through the permission layer, execute the approved tool(s) in the sandbox,
  run the verifier, capture the verdict + feedback, advance `t`. Each iteration is one row of the
  §17 instrumentation.
- **Per-run** (whole loop): accumulate iterations until a **stopping condition** (R-08) fires;
  emit `trajectory.json` + a human summary.
- **Per-experiment** (`experiment` subcommand, §17): wrap one or more runs over the
  injection→repair scenario; emit `experiment.json` summarizing the detect/diagnose/repair arc and
  the iteration count.

The **deterministic/probabilistic seam**: `context`, `permissions`, `tools`, `verifier`, and
`loop` are deterministic; only `policy` (its `OllamaPolicy` branch) is probabilistic. On the mock
path no probabilistic component participates (R-13).

### 3.2 The control loop (one run)

```text
              Task (task file / --task string)
                         |
                        v
          +----------------------------------------------------+
          |  OBSERVE    O_t <- environment (sandbox repo state) |
          |  REASON     C_t = ContextManager(task, history, O_t)|
          |              A_t = Policy(C_t, O_t)   [#1 pi_theta] |
          |  PERMIT     decision = PermissionLayer(A_t) [R-05]  |
          |       - if DENY: record, skip, -> next REASON        |
          |  ACT        exec approved tool(s) in SANDBOX [R-04] |
          |              S_{t+1} = T(S_t, A_t)                   |
          |  VERIFY     verdict = Verifier(sandbox)   [R-06]    |
          |  FEEDBACK   if verdict == VERIFIED: STOP (VERIFIED)  |
          |              else: feedback(O_{t+1}) -> OBSERVE      |
          +----------------------------------------------------+
                         |
         stopping condition?                 | yes
   (VERIFIED | BUDGET_EXHAUSTED | STALLED)   v
                         |           trajectory.json (R-09)
                        v               + human summary + exit code (K-03)
```

The agent moves through states `RECEIVED → OBSERVING → REASONING → PERMITTING → ACTING →
VERIFYING → FEEDBACK`, cycling back to `OBSERVING` on any `FAILED` verdict, and settling in a
terminal state `{VERIFIED, BUDGET_EXHAUSTED, STALLED, DENIED_LOOP, ERROR}`. A `DENY` at the
PERMIT stage does **not** end the run — it routes to the next `REASON`; only a *repeated*
denial cycle (`DENIED_LOOP`) or a permission-layer misconfiguration terminates.

### 3.3 The instrumented-artifact pipeline

The agent's *only* durable artifacts are files written by `report.py`:

- `trajectory.json` (from `run`) — the versioned, schema-gated record (C-06): per-iteration rows +
   top-level `final_outcome`, `policy` (`mock`/`ollama`), model-availability banner (R-14), and
   the §17 field set.
- `experiment.json` (from `experiment`) — the versioned record (C-07): the injected-failure
   scenario, per-run `detect`/`diagnose`/`repair` phase markers, the iteration-to-`VERIFIED` count,
   plus the embedded `trajectory.json` ref.

All downstream readers (`inspect`, the optional `--baseline` System-A/B compare, R-18) read **only**
these artifacts — they never re-run the loop or re-touch the sandbox (I-006).

---

## 4. Interfaces / contracts

### C-01 Task specification

```python
# task.py — the input to one run
@dataclass
class Task:
    task_id: str                  # stable id, e.g. "parse-config"
    prompt: str                   # natural-language task (the --task string or task file body)
    target_repo: str              # path to the repo to be copied into the sandbox
    verifier: "VerifySpec"        # C-05: which verification closes the loop
    success_token: str | None = None    # MAY: a substring/regex the repaired artifact must contain
    acceptance_test: str | None = None  # MAY: a specific test id that must pass to count as VERIFIED
```

### C-02 Policy interface

```python
# policy.py — the ONLY module that MAY call the model/network (R-15)
class Policy(Protocol):
    def select(self, context: Context, observation: Observation) -> Action: ...

# Action is a closed tag-union (I-004):
#   ToolCall(name: str, args: dict)    # -> routed to PermissionLayer then ToolController
#   STOP(final_outcome: "VERIFIED")    # policy may declare completion, but only a
#                                       #  VERIFIED verifier may settle the run (see loop)
#   NOOP(note: str)                    # -> feeds STALLED detection (R-08)
```

`MockPolicy` is deterministic: it is a **scripted** list of `Action`s (for fixed acceptance
experiments) or a **rule-driven** policy (read→inspect→search→edit→verify→repair rules, for the
injection experiment). `OllamaPolicy` wraps the model with a fixed **seed** where supported;
otherwise it is labeled `seed=None` and excluded from byte-identity (I-002 applies to the mock
path only).

### C-03 Tool schema (pinned; closed set)

```python
# tools.py — each tool is a (name, input schema, output schema, sandbox-bound) callable
TOOL_SET = {
   "list_files":  {"in":  {"path": str, "glob": str?},                   "out": "list[str]"},
   "read_file":   {"in":  {"path": str},                                 "out": "str"},
   "search":      {"in":  {"query": str, "path_glob": str?},            "out": "list[Hit]"},   # grep-like
   "edit_file":   {"in":  {"path": str, "op": enum[replace|append|prepend], "old"?: str, "new": str},
                    "out": "EditResult{applied: bool, diff: str}"},
   "run_shell":  {"in":  {"command": str, "cwd": str?},                "out": "ProcResult{exit: int, out: str, err: str}"},
}
```

Every tool resolves its `path`/`cwd` strictly *inside* the sandbox root (R-12, I-003). `edit_file`
is the only mutation tool; `run_shell` is used for *verification* (tests/typecheck/lint/build) and
is itself permission-gated.

### C-04 Permission decision

```python
# permissions.py — evaluated BEFORE any tool executes (R-05)
ALLOW = {"tool": str, "args": dict, "reason": "ALLOWED"}
DENY  = {"tool": str, "args": dict, "reason": "NOT_IN_ALLOWLIST" | "PATH_OUTSIDE_SANDBOX"
                                | "COMMAND_FORBIDDEN" | "RULE_DENIED", "detail": str}

def authorize(tool_call: Action, sandbox_root: str, pconfig: PermsConfig) -> "ALLOW | DENY": ...
```

`PermsConfig` declares: `allow_list` (tools/operations, static §11.1), `sandbox_root` + path check
(dynamic §11.2), and MAY a `rule` function (policy-based §11.3). Evaluation precedence: (1)
path-in-sandbox, (2) command-prefix allow for `run_shell`, (3) tool in `allow_list`, (4) MAY rule
override. First `DENY` wins.

### C-05 Verifier specification + verdict

```python
@dataclass
class VerifySpec:
    kind: enum["tests", "typecheck", "lint", "build", "repo_specific"]   # §7.1–5
    command: str            # e.g. "pytest -q" / "python -m mypy" / "python -m ruff"
    success_exit: int = 0

@dataclass
class Verdict:
    status: "VERIFIED" | "FAILED" | "ERROR"    # §7
    checks: list[dict]     # per-check {kind, command, exit, output_tail}
    output: str            # captured stdout/stderr tail; fed into the next OBSERVE (§13)
```

A run *settles* `VERIFIED` only when the verdict is `VERIFIED` for the run's `VerifySpec` (R-06).
`FAILED` (non-zero exit, captured) and `ERROR` (verifier could not run, e.g. import failure / runner
missing) are distinct: `ERROR` is reported but does not by itself terminate (it feeds the next
iteration) unless it recurs (E-03).

### C-06 `trajectory.json` artifact (versioned, R-17)

```jsonc
{
   "trajectory_version": "0.1",
   "task_id": "parse-config",
   "policy": "mock",
   "availability_banner": null,     # set only on DEGRADED_MOCK, else null
   "sandbox_root": "/tmp/agent-sbx/...",
   "iterations": [
     {
       "iteration": 0,
       "tool_calls": [{"name": "list_files", "args": {"path": "."}}, {"name": "read_file", "args": {"path": "src/..."}}],
       "tokens": {"estimated": 1820, "mode": "synthetic"},
       "files_read": ["src/config.py"],
       "files_modified": [],
       "tests_executed": 0,
       "test_results": null,
       "errors": [],
       "time_ms": 42,
       "verdict": "PENDING",
       "phase": "observe|inspect|search|propose|modify|verify|repair|stop"
     }
   ],
   "final_outcome": "VERIFIED",
   "iterations_used": 4,
   "total_tokens": {"estimated": 9140, "mode": "synthetic"}
}
```

The §17 field set (`iteration`, `tool_calls`, `tokens`, `files_read`, `files_modified`,
`tests_executed`, `test_results`, `errors`, `time_per_iteration` → `time_ms`, `final_outcome`)
MUST be present on every iteration row (R-09). `tokens.mode == "synthetic"` when `policy == "mock"`
(R-13/E-04).

### C-07 `experiment.json` artifact (versioned, R-17)

```jsonc
{
   "experiment_version": "0.1",
   "task_id": "parse-config",
   "injection": {"file": "src/config.py", "symbol": "parse_config",
                 "injected_defect": "wrong split delimiter",
                 "pre_injection_verdict": "FAILED"},
   "phases": [
     {"phase": "detect",   "iteration": 1, "evidence": "test_parse_basic FAILS"},
     {"phase": "diagnose", "iteration": 2, "evidence": "delimiter == '=' vs expected '=='"},
     {"phase": "repair",   "iteration": 3, "evidence": "edit_file applied to src/config.py"}
   ],
   "final_outcome": "VERIFIED",
   "iterations_to_verified": 3,
   "trajectory_ref": "trajectory.json"
}
```

The experiment MUST record detect/diagnose/repair (R-11) and the iteration-to-`VERIFIED` count.

### C-08 Stopping conditions and `final_outcome` closure

```text
STOPPING (R-08):
   VERIFIED           -> final_outcome VERIFIED          exit 0
   BUDGET_EXHAUSTED   -> final_outcome BUDGET_EXHAUSTED  exit 1
   STALLED            -> final_outcome STALLED           exit 1   (MAY)
   DENIED_LOOP        -> final_outcome DENIED_LOOP       exit 1   (permission misconfig)
   ERROR              -> final_outcome ERROR             exit 1 / 4
```
