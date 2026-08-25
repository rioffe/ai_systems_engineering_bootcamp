"""model_playground -- an LLM inference substrate (PyQt5 + uv, local Ollama).

See SPEC.md for the authoritative behaviour, contracts, invariants and acceptance
criteria. Modules are derived from that spec (sections 3-5):

    types.py       C-01 core types (Message, GenerationParams, Usage, StreamChunk,
                ModelResponse) -- the interchangeable-model contract (R-01).
    ollama.py      C-03b OllamaClient -- the ONLY provider-aware module (I-002); a
                thin httpx client over the Ollama localhost API.
    model.py       C-02 Model interface + OllamaModel (real) + MockModel (offline
                deterministic double, with slow/raising/empty variants).
    registry.py    C-03 ModelRegistry + ModelSpec (pricing lives only here, I-003)
                + discovery with Ollama-> mock fallback (R-16 / E-13).
    metrics.py     C-04 RunMetrics / compute_metrics (TTFT, TPS, cost, per-task).
    structured.py  C-05 parse -> validate -> retry/fallback (the reliability
                boundary, I-009).
    worker.py      C-06 RunWorker(QThread): one per model, off the UI thread.
    ui.py          section 5 MainWindow + per-model ModelPanel + fallback banner.
    app.py         main() -- the `model-playground` console entry point.

The real backend is Ollama; the test suite and offline runs use MockModel, so the
app imports, builds and tests with no Ollama and no keys (K-04).
"""

__version__ = "0.1.0"
