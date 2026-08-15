## Day 15 — How coding agents work

Study the architecture of a coding agent:

```text
             +---------------+
             |      LLM      |
             +-------+-------+
                     ↓
             +---------------+
             | Agent harness |
             +-------+-------+
                     ↓
       +-------------+-------------+
       ↓             ↓             ↓
   filesystem      shell         tools
       ↓             ↓             ↓
       +-------------+-------------+
                     ↓
                 verifier
                     ↓
                  feedback
                     ↺
```

Study:

* context management
* tool use
* planning
* execution
* verification
* iteration
* compaction
* subagents
* permissions

---