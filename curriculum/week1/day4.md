## Day 4 — Evals

This is probably the most important day of Week 1.

Study:

### Offline evaluation

* golden datasets
* deterministic tests
* LLM-as-judge
* human evaluation
* pairwise evaluation
* rubric-based evaluation

### Metrics

Depending on the application:

* accuracy
* precision/recall
* groundedness
* relevance
* completeness
* hallucination rate
* tool-call success
* latency
* cost

Build an evaluation harness:

```text
Dataset
   ↓
Application
   ↓
Outputs
   ↓
Evaluator
   ↓
Metrics
   ↓
Regression report
```

Then modify your application and watch the evaluation suite catch regressions.

This is where the traditional software-engineering mindset starts merging with AI engineering.

---