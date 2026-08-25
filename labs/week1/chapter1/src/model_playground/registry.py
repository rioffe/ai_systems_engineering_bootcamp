"""C-03 ModelRegistry + pricing, and model discovery (SPEC section 4 / C-03).

Pricing lives ONLY in the registry (I-003); cost_usd is derived, never hard-coded
in the UI or worker. For local Ollama the per-1k prices default to 0.0 (no vendor
bill, R-06) and remain configurable so a nominal compute cost can be booked in.

Discovery (R-16 / E-13): the app tries Ollama's /api/tags; on any failure it falls
back to the built-in MockModel registry. The real GUI uses a reachable Ollama when
there is one; tests inject a registry or force a dead OLLAMA_HOST (T-16).
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import MockModel, OllamaModel
from .ollama import OllamaClient
from .types import Usage


@dataclass(slots=True)
class ModelSpec:
    model: object
    label: str | None = None
    price_input_usd_per_1k: float = 0.0
    price_output_usd_per_1k: float = 0.0

    @property
    def display_label(self) -> str:
        return self.label or self.model.model_id


class ModelRegistry:
    def __init__(self) -> None:
        self._by_id: dict[str, ModelSpec] = {}

    def register(self, spec: ModelSpec) -> None:
        self._by_id[spec.model.model_id] = spec

    def get(self, model_id: str) -> ModelSpec:
        try:
            return self._by_id[model_id]
        except KeyError as exc:
            raise KeyError(model_id) from exc

    def available(self) -> list[ModelSpec]:
        return list(self._by_id.values())

    def cost_usd(self, model_id: str, usage: Usage) -> float:
        spec = self.get(model_id)
        return (
            usage.prompt_tokens / 1000.0 * spec.price_input_usd_per_1k
            + usage.completion_tokens / 1000.0 * spec.price_output_usd_per_1k
        )


def build_default_registry() -> ModelRegistry:
    reg = ModelRegistry()
    reg.register(ModelSpec(MockModel("mock/fast", "fast"), label="Mock Fast"))
    reg.register(ModelSpec(MockModel("mock/slow", "slow"), label="Mock Slow"))
    reg.register(
        ModelSpec(
            MockModel("mock/raising", "raising"), label="Mock Raising (error demo)"
        )
    )
    reg.register(ModelSpec(MockModel("mock/empty", "empty"), label="Mock Empty"))
    return reg


def discover_registry(
    ollama_host: str | None = None,
    client: OllamaClient | None = None,
) -> tuple[ModelRegistry, bool]:
    # Always register the mock variants first, so a run is possible even with no
    # Ollama; then try Ollama /api/tags to add each locally-pulled model. On any
    # failure the mock-only registry stands and used_fallback=True (E-13); the UI
    # states this via a banner. No crash, no hang.
    reg = build_default_registry()
    if client is None:
        client = OllamaClient(base=ollama_host)
    try:
        names = client.list_models()
    except Exception:
        return reg, True
    for name in names:
        reg.register(ModelSpec(OllamaModel(name, client=client), label=name))
    return reg, len(names) == 0


__all__ = [
    "ModelRegistry",
    "ModelSpec",
    "build_default_registry",
    "discover_registry",
]
