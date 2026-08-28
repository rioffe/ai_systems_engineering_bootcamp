## 7. Constraints (precise and measurable)

| ID | Constraint | Measurement |
| ---- | ---------------- | ----- |
| **K-01** | The **test suite** runs fully offline (no Ollama, no network, no embed model) in `< 90`s on a dev box; it never imports, contacts, or pulls the Ollama daemon or `nomic-embed-text` (I-011). | T-14 |
| **K-02** | The deterministic boundary (build_index on the mock + retrieve/hybrid/rerank-mock/context/metrics) runs the **entire default ~100-doc / 25-question dataset** in `< 5`s with all mocks; the real path is exempt. | T-13 |
| **K-03** | Default parameters (all CLI-overridable, §5.1): `k=5`, `top_n=20`, `alpha=0.5`, `hybrid=off`, `rerank=off`, `expand=off`, `contextual=off`, `strategy=heading`, `chunk_size=800` (chars), `overlap=200`, `n_expand=3`, `max_retries=2`, `timeout_s=60`, `seed=42`, `D_mock=256`. | T-13 |
| **K-04** | The deterministic boundary (chunk + vector + hybrid-math + rerank-mock + expand-mock + contextualize + context + citation + metrics) is **network- and LLM/embed-free** — importable and runnable with zero external services (R-20, I-009). | T-02 |
| **K-05** | A single real end-to-end `--model qwen3.8:27b-mlx --embed-model nomic-embed-text` eval of the full default dataset may take minutes (27B inference + per-question judging + embeddings); it is **opt-in / manual only**, **never** in `uv run pytest` (I-011). | §9.5 smoke |

---

