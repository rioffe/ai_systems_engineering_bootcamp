## Day 2 — Context engineering

This deserves substantially more attention than prompting.

Study:

* system/user/tool context
* context windows
* instruction hierarchy
* context compression
* retrieval
* long-context failure modes
* relevance vs completeness
* context pollution
* state vs context
* memory

Then implement:

```text
User
  ↓
Intent analysis
  ↓
Context retrieval
  ↓
Context construction
  ↓
LLM
  ↓
Structured output
```

### Exercise

Give the system 100 documents and ask increasingly difficult questions.

Measure:

* retrieval precision
* retrieval recall
* answer accuracy
* hallucination rate

This naturally introduces **eval-driven development**.

---