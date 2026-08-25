"""C-01 core types (SPEC section 4 / C-01) -- the interchangeable-model contract.

Pure and headless: no Qt, no network, no provider SDK. These dataclasses are the
whole surface the rest of the system agrees on, which is what makes a model
substitutable for another without changing any other layer (R-01, I-002).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Role(str, Enum):
    """Message roles, matching the Ollama/chat-completions convention."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"

    @classmethod
    def coerce(cls, value: str) -> Role:
        try:
            return cls(value)
        except ValueError as exc:
            raise ValueError(f"unknown role: {value!r}") from exc


@dataclass(slots=True)
class Message:
    """A single chat message (role + text content)."""

    role: str
    content: str

    def __post_init__(self) -> None:
        self.role = Role.coerce(self.role).value


@dataclass(slots=True)
class GenerationParams:
    """The generation-parameter set a Model needs (SPEC C-01 / R-02).

    Ranges (clamped at the UI, C-08; validated here for direct callers):
    temperature in [0, 2]; top_p in (0, 1]; max_tokens > 0.
    A fixed `seed` makes a run reproducible when the model honours it (R-15).
    """

    temperature: float = 0.0
    top_p: float = 1.0
    max_tokens: int = 512
    seed: int | None = None

    def validate(self) -> list[str]:
        """Return a list of constraint violations (empty iff valid)."""
        errors: list[str] = []
        if not (0.0 <= self.temperature <= 2.0):
            errors.append("temperature must be in [0, 2]")
        if not (0.0 < self.top_p <= 1.0):
            errors.append("top_p must be in (0, 1]")
        if self.max_tokens < 1:
            errors.append("max_tokens must be >= 1")
        return errors


@dataclass(slots=True)
class Usage:
    """Token usage for a run (SPEC C-01 / R-05). Both counts >= 0 (I-001)."""

    prompt_tokens: int
    completion_tokens: int

    def __post_init__(self) -> None:
        if self.prompt_tokens < 0 or self.completion_tokens < 0:
            raise ValueError("token counts must be >= 0")

    @property
    def total_tokens(self) -> int:
        """I-001: total is the sum of the two component counts."""
        return self.prompt_tokens + self.completion_tokens


@dataclass(slots=True)
class StreamChunk:
    """One streamed piece of a completion (SPEC C-01).

    `delta` may be "" on a keepalive; `finished` is True on the final chunk,
    which carries the final `usage` (I-008). `usage` is None mid-stream.
    """

    delta: str
    finished: bool
    usage: Usage | None = None
    # A reasoning model (e.g. gemma4) streams its chain-of-thought in a separate
    # `thinking` channel while `content` stays empty; empty for non-thinking models.
    thinking: str = ""


@dataclass(slots=True)
class ModelResponse:
    """The non-streaming return, and the *collected* form of a stream (C-01)."""

    text: str
    usage: Usage
    model_id: str
    # Chain-of-thought for reasoning models; "" for models that don't think.
    thinking: str = ""
