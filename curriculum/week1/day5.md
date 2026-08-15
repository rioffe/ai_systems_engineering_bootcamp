## Day 5 — Agentic workflows

Study the progression:

```text
Prompt
  ↓
LLM
```

→

```text
Prompt
  ↓
LLM
  ↓
Tool
```

→

```text
Planner
  ↓
Tool
  ↓
Observation
  ↓
Reasoning
  ↓
Tool
  ↓
...
```

Topics:

* agents vs workflows
* tool calling
* planning
* state
* loops
* retries
* reflection
* delegation
* stopping conditions
* permissions
* failure recovery

Build a small agent that can:

* search
* retrieve information
* call tools
* reason over results
* produce a final report

Then introduce failures deliberately.

---