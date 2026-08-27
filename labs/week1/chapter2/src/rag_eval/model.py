"""C-05 the LLM -- the single probabilistic role: answer generation (SPEC R-05/R-17).

Two implementations behind one interface (R-01):

* ``MockLLM``    -- a deterministic, offline, bitwise-reproducible double that needs no
    Ollama and no network (R-14/I-011). It authors a schema-valid grounded answer from
    the context -- citing only doc ids that appear in it (I-003) -- so the whole
    automated suite runs without a model. A ``hallucinate`` knob inserts a claim grounded
    in a doc id that is *not* in the context, so the downstream grounding gate (E-08) and
    the hallucination metric (R-09) are exercised deterministically.
* ``OllamaLLM`` -- the real backend, a thin httpx client over the local Ollama
    ``/api/chat`` + ``/api/tags`` (E-11/E-12/E-13). This module is the *only* one in the
    system to name a provider URL / provider JSON shape (the ch1 I-002 seam, pinned by
    T-02); it imports ``httpx`` (allowed only here + judgment.py).

Both funnel through ``schemas.generate_structured`` (the ch1 C-05 parse -> validate ->
error-informed-retry boundary): a generation that exhausts its retries yields
``Answer(status="ERROR")`` and *never* an unvalidated dict (I-010).
"""

from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod

import httpx

from .schemas import (
    ANSWER_SCHEMA,
    DEFAULT_MAX_RETRIES,
    build_retry_directive,
    generate_structured,
)
from .types import Answer, Usage

# The local Ollama endpoint; overridable via OLLAMA_HOST (matches ch1).
OLLAMA_BASE = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# Extract the [NNN] provenance labels the context builder emits (I-003 grounding).
_LABEL = re.compile(r"\[(?P<id>\d+)\]")
# A foreign citation id the hallucinating double invents (E-08: not in the context).
HALLUCINATED_ID = "HALL-01"

# The one system prompt every model sees (ch1 style): "emit the answer schema as JSON".
_ANSWER_SYSTEM = (
    "You are a grounded RAG answerer. Using ONLY the retrieved documents, answer the "
    "question. Respond with a SINGLE valid JSON object (no prose, no markdown fences) of "
    'the form {"answer": string, "confidence": number in [0,1], '
    '"sources": array of doc ids from the provided documents only}. '
    "Cite ONLY document ids present in the retrieved context. "
    'If no document answers the question, answer "I cannot answer from the provided '
    'documents." with an empty sources array.'
)


class OllamaError(Exception):
    """A transport/detection fault (E-11): unreachable daemon, bad HTTP.

    A caller (the CLI) treats this as "Ollama unavailable -> fall back to mock" when
    no model was forced, or exit 4 when an explicit model was requested.
    """


class ModelNotFoundError(OllamaError):
    """E-12 / T-18 analog: an unpulled model (Ollama 404). Carries the pull hint."""


def model_not_found_error(name: str) -> str | None:
    """The E-12 pull hint for an unpulled model (a plain string, for the CLI banner)."""
    return f"model not found: {name!r} -- pull it with: ollama pull {name}"


def _options(max_tokens: int, temperature: float, seed: int | None) -> dict:
    # Ollama `options` mapping (ch1 C-03b): num_predict<-max_tokens; seed omitted when None.
    opts: dict = {"temperature": temperature, "num_predict": max_tokens}
    if seed is not None:
        opts["seed"] = seed
    return opts


class OllamaClient:
    """The ONLY provider-aware object (I-002): it names the Ollama URL shape and parses
    ``/api/tags`` + ``/api/chat``. Everything else sees a Model + Answer only.

    It degrades gracefully: an unreachable daemon raises :class:`OllamaError` (E-11), an
    unpulled model raises :class:`ModelNotFoundError` (E-12), and a malformed body is
    mapped to a best-effort usage -- never a crash.
    """

    def __init__(
        self,
        base: str | None = None,
        timeout_s: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base = (base or OLLAMA_BASE).rstrip("/")
        self.timeout_s = timeout_s
        self._transport = transport

    def _client(self) -> httpx.Client:
        kwargs: dict = {"timeout": self.timeout_s}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.Client(**kwargs)

    def list_models(self) -> list[str]:
        # R-16 discovery: GET /api/tags. An unreachable daemon raises OllamaError.
        try:
            with self._client() as client:
                resp = client.get(self.base + "/api/tags")
        except httpx.HTTPError as exc:
            raise OllamaError(f"ollama not reachable: {exc}") from exc
        if resp.status_code != 200:
            raise OllamaError(
                f"Ollama /api/tags HTTP {resp.status_code}: {resp.text[:200]}"
            )
        return [str(m["name"]) for m in resp.json().get("models", []) if m.get("name")]

    def chat(
        self,
        model: str,
        sys_prompt: str,
        user_prompt: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
        seed: int | None = None,
    ) -> tuple[str, Usage, bool]:
        # POST /api/chat (non-stream); returns (text, Usage). 404 -> ModelNotFoundError.
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "options": _options(max_tokens, temperature, seed),
            "stream": False,
        }
        try:
            with self._client() as client:
                resp = client.post(self.base + "/api/chat", json=payload)
        except httpx.HTTPError as exc:
            raise OllamaError(f"ollama not reachable: {exc}") from exc
        if resp.status_code == 404:
            raise ModelNotFoundError(
                f"model not found: '{model}' -- pull it with: ollama pull {model}"
            )
        if resp.status_code != 200:
            raise OllamaError(
                f"Ollama /api/chat HTTP {resp.status_code}: {resp.text[:200]}"
            )
        data = resp.json()
        message = data.get("message") or {}
        text = message.get("content") or ""
        prompt_eval = data.get("prompt_eval_count") or 0
        eval_count = data.get("eval_count") or 0
        try:
            usage = Usage(int(prompt_eval), int(eval_count))
        except (TypeError, ValueError):
            usage = Usage(0, len(text.split()))  # best-effort on a malformed body
        # truncated: content empty while a thinking trace is present (thinking ate budget)
        truncated = not text.strip() and bool(
            str(message.get("thinking") or "").strip()
        )
        return text, usage, truncated


def _context_ids(context: str) -> list[str]:
    # The distinct provenance ids the context labels ([001]-> "001"), in first-seen order.
    seen: set[str] = set()
    out: list[str] = []
    for m in _LABEL.finditer(context or ""):
        doc_id = m.group("id")
        if doc_id not in seen:  # keep first occurrence; deterministic order
            seen.add(doc_id)
            out.append(doc_id)
    return out


class LLM(ABC):
    """C-05: an LLM produces a grounded, structured §19 answer via the schema gate.

    Subclasses implement ``_raw`` (the actual model call); ``generate`` owns the shared
    parse -> validate -> error-informed-retry loop over ``ANSWER_SCHEMA``.
    """

    #: each subclass records its last Usage here so generate() can attach it (I-010).
    _usage: Usage
    #: last-attempt truncation: num_predict spent on a hidden thinking block.
    _truncated: bool

    @property
    @abstractmethod
    def model_id(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def _raw(
        self,
        sys_prompt: str,
        user_prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        seed: int | None,
    ) -> str:
        raise NotImplementedError

    def generate(
        self,
        *,
        system: str,
        context: str,
        question: str,
        max_tokens: int = 512,
        temperature: float = 0.0,
        seed: int | None = 42,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> Answer:
        # parse -> validate -> error-informed-retry over ANSWER_SCHEMA (ch1 C-05).
        base = f"{_ANSWER_SYSTEM}\n{system}"
        last_directive: str | None = None
        self._usage = Usage(0, 0)
        self._truncated = False

        def prompt_for_attempt(attempt: int, last):
            nonlocal last_directive
            if last is not None and not last.ok:
                last_directive = build_retry_directive(ANSWER_SCHEMA, last)
            user = _user_prompt(context, question, last_directive)
            return self._raw(
                base,
                user,
                max_tokens=max_tokens,
                temperature=temperature,
                seed=seed,
            )

        structured = generate_structured(
            prompt_for_attempt, ANSWER_SCHEMA, max_retries=max_retries
        )
        if not structured.ok:
            truncated = bool(getattr(self, "_truncated", False))
            # thinking ate num_predict -> TRUNCATED, not a silent parse ERROR (E-10/E-11)
            return Answer(
                q_id="",
                text="",
                confidence=0.0,
                sources=[],
                usage=self._usage,
                status="TRUNCATED" if truncated else "ERROR",
                truncated=truncated,
            )
        data = structured.data
        assert data is not None  # structured.ok implies data present (I-010)
        return Answer(
            q_id="",
            text=str(data["answer"]),
            confidence=_coerce_confidence(data),
            sources=[str(s) for s in data.get("sources", [])],
            usage=self._usage,
            status="COMPLETED",
            truncated=bool(getattr(self, "_truncated", False)),
        )


class MockLLM(LLM):
    """A deterministic, offline, bitwise-reproducible double (R-14/R-15).

    The produced answer cites only ids present in the context; ``hallucinate`` appends a
    foreign citation (E-08 / T-08a); ``_always_bad`` drives the exhausted-retry ERROR path.
    For a fixed context the output is seed-independent and therefore bitwise reproducible.
    """

    HALLUCINATED_TEXT = " A corroborating figure of 8742 appears in file HALL-01."

    def __init__(self, hallucinate: bool = False, seed: int | None = 42) -> None:
        self._id_ = "mock"
        self._hallucinate = hallucinate
        self._always_bad = False
        self._seed = seed
        self._usage = Usage(0, 0)

    @property
    def model_id(self) -> str:
        return self._id_

    def _raw(
        self,
        sys_prompt: str,
        user_prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        seed: int | None,
    ) -> str:
        # Derive a schema-valid JSON string from the context (deterministic, grounded).
        if self._always_bad:
            return "not valid json at all {"
        ids = _context_ids(user_prompt)
        if not ids:
            answer = "I cannot answer from the provided documents."
            confidence = 0.0
        else:
            rest = ", ".join(ids[1:]) if len(ids) > 1 else ids[0]
            answer = (
                f"The answer is grounded in {ids[0]} ({rest}): see the retrieved context "
                f"for the supporting documents."
            )
            confidence = 0.9
        if self._hallucinate:
            answer = f"{answer}{self.HALLUCINATED_TEXT}"
        payload = {
            "answer": answer,
            "confidence": confidence,
            "sources": ids + ([HALLUCINATED_ID] if self._hallucinate else []),
        }
        # Deterministic usage: whitespace counts of the prompts (stable across runs).
        self._usage = Usage(len(user_prompt.split()), len(json.dumps(payload).split()))
        return json.dumps(payload)


class OllamaLLM(LLM):
    """The real backend (R-16): delegates every call to an :class:`OllamaClient`."""

    def __init__(
        self,
        name: str,
        client: OllamaClient | None = None,
        model_id: str | None = None,
    ) -> None:
        self._name = name
        self._client = client if client is not None else OllamaClient()
        self._id_ = model_id or name
        self._usage = Usage(0, 0)

    @property
    def model_id(self) -> str:
        return self._id_

    @property
    def ollama_name(self) -> str:
        return self._name

    def _raw(
        self,
        sys_prompt: str,
        user_prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        seed: int | None,
    ) -> str:
        # Fatal transport faults (E-11/E-12) propagate to the CLI; parse/validation
        # failures are handled by the surrounding generate_structured retry loop.
        text, usage, truncated = self._client.chat(
            self._name,
            sys_prompt,
            user_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            seed=seed,
        )
        self._usage = usage
        self._truncated = truncated
        return text


def _coerce_confidence(data: dict) -> float:
    # Defensive number coercion; the schema already bounds confidence to [0,1] (I-010).
    try:
        return float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _user_prompt(context: str, question: str, directive: str | None) -> str:
    parts = [f"RETRIEVED DOCUMENTS:\n{context}", f"QUESTION:\n{question}"]
    if directive:
        parts.append(f"RETRY DIRECTIVE (fix the previous attempt): {directive}")
    return "\n\n".join(parts)


__all__ = [
    "ANSWER_SCHEMA",
    "HALLUCINATED_ID",
    "LLM",
    "OLLAMA_BASE",
    "MockLLM",
    "ModelNotFoundError",
    "OllamaClient",
    "OllamaError",
    "OllamaLLM",
    "model_not_found_error",
]
