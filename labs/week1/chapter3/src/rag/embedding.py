"""Embedders -- O-1 MockEmbedder (deterministic hashed bag-of-words) + OllamaEmbedder.

Implements C-02 / R-02 / O-1 from SPEC.md. The MockEmbedder is the offline
double that makes the dense boundary testable without any embed model or
network. The OllamaEmbedder is the real path, used only in the manual smoke.
"""

from __future__ import annotations

import abc
import math
import re

from loguru import logger

FNV_OFFSET = 0x811C9DC5
FNV_PRIME = 0x01000193
FNV_MASK = 0xFFFFFFFF

# O-1a tokenizer: lowercase, split on [^\w']+, drop empty.
_TOKEN_RE = re.compile(r"[^\w']+")


def fnv1a32(text: str) -> int:
    # FNV-1a 32-bit. Process-independent (NOT Python's built-in hash).
    h = FNV_OFFSET
    for byte in text.encode("utf-8"):
        h ^= byte
        h = (h * FNV_PRIME) & FNV_MASK
    return h


def tokenizer(text: str) -> list[str]:
    # Lowercase, split on [^\w']+, drop empty (O-1a, same as ch2 BM25).
    raw = _TOKEN_RE.split(text.lower())
    return [t for t in raw if t]


class Embedder(abc.ABC):
    """Abstract interface; concrete subclasses provide model_id + dim."""
    model_id: str = ""
    dim: int = 256

    @abc.abstractmethod
    def embed(self, text: str) -> tuple[float, ...]:
        """Return a dense vector of size `dim` for the given text."""

class MockEmbedder(Embedder):
    # O-1: deterministic hashed bag-of-words, L2-normalized, process-independent.
    model_id = "mock"

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def embed(self, text: str) -> tuple[float, ...]:
        toks = tokenizer(text)
        vec = [0.0] * self.dim
        for t in toks:
            idx = fnv1a32(t) % self.dim
            vec[idx] += 1.0
        norm_sq = sum(x * x for x in vec)
        norm = math.sqrt(norm_sq) if norm_sq > 0.0 else 1.0
        return tuple(x / norm for x in vec)


class OllamaEmbedder(Embedder):
    # Real path: POST /api/embed {model, prompt} -> embedding[0].
    # Used only in the manual smoke (K-05); never in the test suite (I-011).
    dim = 768  # nomic-embed-text default dimension.

    def __init__(
        self,
        *,
        model: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
        dim: int | None = None,
    ) -> None:
        self.model = model
        self.model_id = model
        self.base_url = base_url
        if dim is not None:
            self.dim = dim
        logger.debug("OllamaEmbedder: model={} base_url={}", model, base_url)

    def embed(self, text: str) -> tuple[float, ...]:
        import httpx

        resp = httpx.post(
            f"{self.base_url}/api/embed",
            json={"model": self.model, "prompt": text},
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
        # /api/embed returns either {"embeddings": [[...]]} or {"embedding": [...]}.
        raw = data.get("embeddings") or data.get("embedding")
        if raw is None:
            raise ValueError("unexpected /api/embed response shape")
        if isinstance(raw, list) and raw and isinstance(raw[0], list):
            raw = raw[0]
        try:
            return tuple(float(x) for x in raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"bad embedding vector in /api/embed response: {exc}") from exc
