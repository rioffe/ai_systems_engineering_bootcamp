# Chapter 5: Bounded Research-Agent Runtime

This lab implements a bounded agent loop around one policy boundary. The policy proposes the next
action; deterministic runtime code validates, authorizes, executes, retries, records, and stops.

## Setup

Requires Python 3.12 and `uv`.

```bash
cd labs/week1/chapter5
unset VIRTUAL_ENV
uv sync --extra dev
```

Optional GUI dependencies:

```bash
uv sync --extra gui
```

The default workflow is offline. It uses `MockPolicy` and the version-controlled local corpus in
`corpus/`; no Ollama daemon or model is required.

## Quick start

```bash
# Run a bounded research episode and write a versioned trace.
uv run research-agent run \
  --question "What is the reimbursement limit?" \
  --mock \
  --out trace.json

# Render the saved trace without running inference again.
uv run research-agent trace trace.json

# Execute one deterministic failure drill.
uv run research-agent drill \
  --name malformed_arguments \
  --out drill_report.json

# Verify the deterministic import boundary.
uv run research-agent --self-check
```

## CLI

### `run`

```text
research-agent run --question TEXT --out trace.json
  [--mock | --real] [--budgets budgets.yml] [--corpus corpus/]
```

`run` loads the local corpus and optional budget configuration, selects `MockPolicy` by default or
`OllamaPolicy` with `--real`, runs one bounded episode, validates the final report, and writes
`trace.json`. The policy never executes tools or controls termination.

The trace includes the deterministic `run_id`, model/prompt metadata, typed reasoning/action/
observation entries, retries, token/cost surrogates, final report, termination reason, and loop
metrics. `insufficient_evidence` is a successful report status when the corpus cannot justify an
answer.

Exit codes:

- `0`: completed, including `insufficient_evidence` and `DEGRADED_MOCK`
- `2`: usage, config, corpus, or artifact error
- `3`: reserved corpus-integrity violation
- `4`: `PULL_REQUIRED` when a real model is unavailable

### `drill`

```text
research-agent drill --name NAME --out drill_report.json
  [--budgets budgets.yml]
```

The supported drill names are:

```text
search_timeout
empty_results
malformed_arguments
retrieval_failure
duplicate_searches
contradictory_sources
low_quality_sources
infinite_loop
max_steps_exhaustion
unauthorized_tool_call
```

Drills are mock-only and inject faults at the policy/tool boundary. Each report contains the four
Chapter 5 questions—model behavior, runtime behavior, expected behavior, and instrumentation—plus
an honest pass/fail verdict. Exit `0` means the pinned expectation passed; exit `1` means the drill
terminated incorrectly; exit `2` means usage/configuration failed.

### `trace`

```text
research-agent trace trace.json
```

Loads a schema-validated trace and renders its typed step timeline, final termination reason, and
policy-facing events. It never runs the policy or tools.

### `--self-check`

```bash
uv run research-agent --self-check
```

Checks that the deterministic runtime core does not import `httpx`, Ollama, or another LLM client.
Only `policy.py` is allowed to cross that boundary.

## Configuration

Default budgets are:

```yaml
max_steps: 10
max_tokens: 20000
max_cost_usd: 0.50
max_seconds: 120
max_retries: 2
repeat_threshold: 3
max_consecutive_failures: 3
```

All keys are schema-validated. Unknown keys and malformed YAML are configuration errors; defaults
are not silently substituted for malformed files.

Authorization is declarative and default-deny:

```yaml
version: 1
rules:
  - {tool: search, effect: allow}
  - {tool: retrieve, effect: allow}
  - {tool: delete_file, effect: deny}
default: deny
```

`search` and `retrieve` are the only operational tools. `delete_file` is registered so the policy
can see it, but the authorization engine always denies it and no filesystem operation is exposed.

## Artifacts and schemas

Schemas are stored in `schemas/` and are applied on every artifact load:

- `trace.json` — episode metadata, typed steps, termination, final report, and loop metrics
- `drill_report.json` — drill name, trace path, four-question analysis, and verdict
- `decision.json` — canonical `tool_call` or `final` policy decision
- `report.json` — final report with status, answer, citations, conflicts, and caveats
- `budgets.json`, `policy.json`, `tool.json` — configuration and tool contracts

Artifacts are canonical JSON with sorted keys, four-decimal float precision, deterministic run IDs,
and no timestamps or absolute paths.

## Metrics and reliability mechanisms

Loop metrics include steps used, tool-call mix, invalid-argument count, repair success, retry and
denial counts, unnecessary-call estimate, termination reason, latency, token totals, and cost
surrogates. The runtime enforces these mechanisms before allowing the next policy call:

1. Budget and stopping-condition check
2. Policy decision
3. Decision validation
4. Authorization
5. Tool execution with class-specific retry
6. Explicit state and trace update

The closed termination reasons are `goal_complete`, `max_steps`, `token_budget`, `cost_budget`,
`time_budget`, `repeated_state`, and `consecutive_tool_failures`.

## Optional GUI

```bash
uv sync --extra gui
uv run research-agent-gui
```

The GUI is read-only and never invokes the runtime, tools, or policy. The command-line `trace`
command is the primary artifact browser in headless environments.

## Project layout

```text
chapter5/
+-- corpus/                  # deterministic local fixture corpus
+-- schemas/                 # JSON Schemas
+-- src/research_agent/
|   +-- policy.py            # MockPolicy and optional OllamaPolicy
|   +-- runtime.py           # sole control loop
|   +-- state.py             # explicit AgentState and surrogates
|   +-- tools.py             # search/retrieve registry
|   +-- validate.py          # decision and report gates
|   +-- authorize.py         # declarative authorization
|   +-- budgets.py           # stopping conditions
|   +-- retry.py             # total failure taxonomy
|   +-- trace.py             # typed trace recorder
|   +-- metrics.py           # pure loop metrics
|   +-- drills.py            # ten fault specifications
|   +-- report.py            # canonical artifact I/O
|   +-- cli.py               # research-agent commands
|   +-- ui.py                # optional read-only GUI
+-- tests/                   # offline test suite
```

## Verification

```bash
unset VIRTUAL_ENV
uv run python -m pytest tests -q
uv run ruff check src tests
uv run research-agent --self-check
```

The real Ollama path is opt-in and best-effort. The automated suite is intentionally offline and
uses deterministic policy/tool doubles.
