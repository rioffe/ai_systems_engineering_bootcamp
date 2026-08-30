# Chapter 4: Evaluation Harness

Install the local environment with `uv sync --extra dev`.

```bash
uv run rag-eval check --dataset tests/fixtures/golden-5.json
uv run rag-eval run --mock --dataset tests/fixtures/golden-5.json --corpus documents --out eval.json
uv run rag-eval compare --baseline eval.json --current eval.json
uv run rag-eval gates --baseline eval.json --current eval.json --config gates.yml
```

The mock path is offline and deterministic. `aoe.py` is the only module that crosses into the Chapter 3 RAG application; downstream commands consume artifacts only.
