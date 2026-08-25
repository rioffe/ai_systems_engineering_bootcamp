"""C-03b OllamaClient -- the ONLY provider-aware module in the system (I-002).

A thin httpx client over the Ollama localhost HTTP API (/api/tags, /api/chat).
No vendor SDK is imported; httpx is a generic HTTP client used only here. This
module is the only one that names URLs or provider-specific JSON shapes; every
other module sees Model + Message + GenerationParams and a ModelSpec registry.

The client degrades gracefully (E-13/E-14/E-15): an unreachable daemon surfaces
as an exception the caller treats as "Ollama unavailable -> fall back to mock";
an unpulled model surfaces as ModelNotFoundError (-> panel ERROR, not a crash);
a malformed NDJSON line is skipped with a best-effort usage, never a crash.
"""

from __future__ import annotations

import json
import os

import httpx

from .types import GenerationParams, ModelResponse, StreamChunk, Usage

# Default local Ollama endpoint; overridable via the OLLAMA_HOST env var.
OLLAMA_BASE = os.environ.get("OLLAMA_HOST", "http://localhost:11434")


class OllamaError(Exception):
    pass


class ModelNotFoundError(OllamaError):
    pass


def _options(params: GenerationParams) -> dict:
    # Map GenerationParams -> Ollama `options` (C-03b mapping): temperature->temperature,
    # top_p->top_p, max_tokens->num_predict, seed->seed (omitted when None).
    base = {
        "temperature": params.temperature,
        "top_p": params.top_p,
        "num_predict": params.max_tokens,
    }
    if params.seed is not None:
        base["seed"] = params.seed
    return base


def _best_effort_usage(text_parts: list[str], thinking_parts: list[str] | None = None) -> Usage:
    # E-15 fallback when a stream ends without a usable `done` line, or a reasoning
    # model put every token in the thinking channel: a rough whitespace count of the
    # accumulated text plus thinking; 0 prompt tokens.
    text = "".join(text_parts) + "".join(thinking_parts or [])
    return Usage(0, len(text.split()))


class OllamaClient:
    # A tiny httpx transport over /api/tags and /api/chat (C-03b).
    def __init__(
        self,
        base: str | None = None,
        timeout_s: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base = (base or OLLAMA_BASE).rstrip("/")
        self.timeout_s = timeout_s
        self._transport = transport

    def _client(self) -> httpx.Client:
        kwargs = {"timeout": self.timeout_s}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.Client(**kwargs)

        # -- discovery (R-16 / E-13) --

    def list_models(self) -> list[str]:
        with self._client() as client:
            resp = client.get(self.base + "/api/tags")
        if resp.status_code != 200:
            raise OllamaError(
                f"Ollama /api/tags HTTP {resp.status_code}: {resp.text[:200]}"
            )
        names: list[str] = []
        for model in resp.json().get("models", []):
            name = model.get("name")
            if name:
                names.append(str(name))
        return names

        # -- chat / completion (C-03b / E-14 / E-15) --

    def chat(
        self, model: str, messages, params: GenerationParams, stream: bool
    ) -> ModelResponse:
        payload = self._payload(model, messages, params, stream)
        with self._client() as client:
            resp = client.post(self.base + "/api/chat", json=payload)
        if resp.status_code == 404:
            raise ModelNotFoundError(
                f"model not found: '{model}' -- pull it with 'ollama pull {model}'"
            )
        if resp.status_code != 200:
            raise OllamaError(
                f"Ollama /api/chat HTTP {resp.status_code}: {resp.text[:200]}"
            )
        data = resp.json()
        message = data.get("message") or {}
        text = message.get("content") or ""
        thinking = message.get("thinking") or ""
        usage = Usage(
            int(data.get("prompt_eval_count") or 0), int(data.get("eval_count") or 0)
        )
        return ModelResponse(text=text, thinking=thinking, usage=usage, model_id=model)

    def stream_chat(self, model, messages, params):
        payload = self._payload(model, messages, params, True)
        with (
            self._client() as client,
            client.stream("POST", self.base + "/api/chat", json=payload) as resp,
        ):
            if resp.status_code == 404:
                resp.read()
                raise ModelNotFoundError(
                    f"model not found: '{model}' -- pull it with 'ollama pull {model}'"
                )
            if resp.status_code != 200:
                raise OllamaError(f"Ollama /api/chat HTTP {resp.status_code}")
            text_parts: list[str] = []
            thinking_parts: list[str] = []
            usage: Usage | None = None
            for raw_line in resp.iter_lines():
                if not raw_line or raw_line.strip() == "":
                    continue
                try:
                    obj = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                delta = ""
                thinking = ""
                message = obj.get("message")
                if isinstance(message, dict):
                    delta = message.get("content") or ""
                    thinking = message.get("thinking") or ""
                if thinking:
                    thinking_parts.append(thinking)
                if obj.get("done"):
                    try:
                        usage = Usage(
                            int(obj.get("prompt_eval_count") or 0),
                            int(obj.get("eval_count") or 0),
                        )
                    except (TypeError, ValueError):
                        usage = _best_effort_usage(text_parts, thinking_parts)
                    yield StreamChunk(delta, True, usage, thinking)
                    return
                if delta or thinking:
                    if delta:
                        text_parts.append(delta)
                    yield StreamChunk(delta, False, None, thinking)
            yield StreamChunk("", True, usage or _best_effort_usage(text_parts, thinking_parts))

    @staticmethod
    def _payload(model, messages, params, stream) -> dict:
        return {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "options": _options(params),
            "stream": stream,
        }


__all__ = [
    "OLLAMA_BASE",
    "ModelNotFoundError",
    "OllamaClient",
    "OllamaError",
    "_options",
]
