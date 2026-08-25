"""C-02 the Model interface and its two implementations (SPEC section 4 / C-02).

Model is the minimal interchangeable surface (R-01): the rest of the system never
names a provider, a concrete model, or a request shape -- only Model, Message,
GenerationParams. Two implementations:

    - OllamaModel: the real backend, delegated entirely to OllamaClient (C-03b).
    - MockModel:   a deterministic, offline, reproducible test double that also
    supplies the "slow", "raising" and "empty" variants used by the failure
    semantic tests (E-02 / E-05 / E-07 / K-02).

MockModel imports only `types` (no httpx, no Ollama): a run/test needs no Ollama
and no keys (K-04). OllamaModel imports the client, so httpx lives only in
ollama.py (I-002).
"""

from __future__ import annotations

import hashlib
import time
from abc import ABC, abstractmethod

from .types import GenerationParams, ModelResponse, StreamChunk, Usage

FAST = "mock/fast"
SLOW = "mock/slow"
RAISING = "mock/raising"
EMPTY = "mock/empty"

_KIND_FAST = "fast"
_KIND_SLOW = "slow"
_KIND_RAISING = "raising"
_KIND_EMPTY = "empty"


class Model(ABC):
    @property
    @abstractmethod
    def model_id(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate(self, messages, temperature=0.0, top_p=1.0, max_tokens=512, seed=None):
        raise NotImplementedError

    @abstractmethod
    def stream(self, messages, temperature=0.0, top_p=1.0, max_tokens=512, seed=None):
        raise NotImplementedError

    @staticmethod
    def _require_nonempty(messages) -> None:
        if not messages:
            raise ValueError("messages must be non-empty")

    @staticmethod
    def _parse_kwargs(temperature=0.0, top_p=1.0, max_tokens=512, seed=None):
        return GenerationParams(temperature, top_p, max_tokens, seed)


class MockModel(Model):
    # A deterministic, offline test double for Model (SPEC section 10). For a
    # fixed `seed` the produced text and usage are bitwise-reproducible
    # (I-012 / R-15); the streamed token count equals the non-streaming usage
    # (I-008). Variants (`kind`) drive the failure-semantic tests, no network:
    #   "fast"    normal (default): a handful of deterministic tokens.
    #   "slow"    like fast but sleeps between tokens (distinct worker thread).
    #   "raising" raises mid-stream and in generate() (E-02 / E-07 demo).
    #   "empty"   an empty response: 0 completion tokens (E-05).

    SLOW_TOKEN_DELAY_S = 0.03

    def __init__(self, model_id: str = FAST, kind: str = _KIND_FAST) -> None:
        self._id = model_id
        self._kind = (kind or _KIND_FAST).split("/")[-1].lower()

    @property
    def model_id(self) -> str:
        return self._id

    @classmethod
    def _words(cls, prompt_text, params):
        # Deterministic, bitwise-stable for a fixed seed (I-012); honors max_tokens.
        seed = params.seed if params.seed is not None else 0
        key = f"{seed}|{params.temperature}|{params.top_p}|{params.max_tokens}|{prompt_text}"
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        n = 4 + (digest[0] % 12)
        n = max(1, min(n, max(1, params.max_tokens)))
        out: list[str] = []
        for i in range(n):
            out.append(f"{i:02d}{digest[i % len(digest)]:02x}")
        return out

    @classmethod
    def _prompt_tokens(cls, messages):
        joined = " ".join(m.content for m in messages)
        return len(joined.split())

    def generate(self, messages, temperature=0.0, top_p=1.0, max_tokens=512, seed=None):
        self._require_nonempty(messages)
        params = self._parse_kwargs(temperature, top_p, max_tokens, seed)
        if self._kind == _KIND_RAISING:
            raise RuntimeError("mock: simulated generation failure")
        if self._kind == _KIND_EMPTY:
            words = []
        else:
            words = self._words(" ".join(m.content for m in messages), params)
        usage = Usage(self._prompt_tokens(messages), len(words))
        return ModelResponse(text=" ".join(words), usage=usage, model_id=self._id)

    def stream(self, messages, temperature=0.0, top_p=1.0, max_tokens=512, seed=None):
        self._require_nonempty(messages)
        params = self._parse_kwargs(temperature, top_p, max_tokens, seed)
        if self._kind == _KIND_EMPTY:
            yield StreamChunk("", True, Usage(self._prompt_tokens(messages), 0))
            return
        words = self._words(" ".join(m.content for m in messages), params)
        usage = Usage(self._prompt_tokens(messages), len(words))
        for i, word in enumerate(words):
            if self._kind == _KIND_RAISING and i == 2:
                raise RuntimeError("mock: simulated mid-stream failure")
            if self._kind == _KIND_SLOW and i > 0:
                time.sleep(self.SLOW_TOKEN_DELAY_S)
            delta = word if i == 0 else " " + word
            finished = i == len(words) - 1
            yield StreamChunk(delta, finished, usage if finished else None)


class OllamaModel(Model):
    def __init__(self, name, client=None, model_id=None) -> None:
        from .ollama import OllamaClient

        self._name = name
        self._client = client if client is not None else OllamaClient()
        self._id = model_id or (f"/ollama/{name}")

    @property
    def model_id(self) -> str:
        return self._id

    @property
    def ollama_name(self) -> str:
        return self._name

    def generate(self, messages, temperature=0.0, top_p=1.0, max_tokens=512, seed=None):
        self._require_nonempty(messages)
        return self._client.chat(
            self._name,
            self._parse_kwargs(temperature, top_p, max_tokens, seed),
            stream=False,
        )

    def stream(self, messages, temperature=0.0, top_p=1.0, max_tokens=512, seed=None):
        self._require_nonempty(messages)
        yield from self._client.stream_chat(
            self._name,
            self._parse_kwargs(temperature, top_p, max_tokens, seed),
        )


__all__ = ["EMPTY", "FAST", "RAISING", "SLOW", "MockModel", "Model", "OllamaModel"]
