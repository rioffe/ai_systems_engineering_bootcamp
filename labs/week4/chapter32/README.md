# Chapter 32: `synthgen`

`synthgen` generates deterministic-first JSONL evaluation datasets. It samples a structured scenario, calculates ground truth with the Chapter 31 mortgage calculator adapter, realizes controlled language, validates the realization, deduplicates it, and publishes reproducible artifacts.

## Setup

```bash
uv sync --extra test
uv sync --extra gui  # optional PyQt5 GUI
```

## Commands

```bash
uv run synthgen generate examples/mortgage.yaml --size 30 --seed 42
uv run synthgen preview examples/mortgage.yaml --size 5
uv run synthgen validate evals/generated.jsonl
uv run synthgen stats evals/generated.jsonl
uv run synthgen inspect evals/generated.jsonl
uv run synthgen reproduce evals/manifest.json
```

The template path is offline and deterministic. `--method ollama --model llama3 --host http://127.0.0.1:11434` enables the bounded optional model adapter. `--verbose` emits INFO metadata; `--verbose DEBUG` includes bounded raw model payload diagnostics. Generated records never accept model-provided ground truth.

The only Chapter 31 dependency is `src/synthgen/truth.py`, which translates a `Scenario` into Chapter 31's `CalculationRequest` and translates its result into the generic `GroundTruth` contract. A different calculator can be registered without changing scenario, validation, reporting, or CLI code.

Each generation writes sorted UTF-8 JSONL plus a report and manifest. The manifest records the specification hash, seed, adapter, paths, and dataset hash. Failed complete runs publish no artifacts; `--allow-partial` explicitly publishes `complete=false` artifacts.
