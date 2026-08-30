"""C-02 the Policy interface and its two implementations (SPEC section 4 / R-15).

The `Policy` interface, `Policy.select(context, observation)`, is the ONLY place
the model may be reached -- the deterministic harness core is otherwise
LLM-/network-free (R-15 / I-009). `Action` is the closed tag-union the loop
consumes (I-004 / C-02):

    ToolCall(name, args)   -> routed to the permission layer, then the tool
                             controller (R-05 / R-04).
    STOP(final_outcome)    -> the policy's *declaration* of completion; only a
                             verifier VERIFIED may actually settle the run
                             (I-006 -- a bare STOP is a promise, not a verdict).
    NOOP(note)             -> feeds STALLED / DENIED_LOOP detection (R-08 / K-08).

Two implementations live behind the interface:
    MockPolicy   -- deterministic, offline. A scripted list of per-iteration
                   batches (or a rule-driven policy, the same surface). Byte-stable
                   (R-13 / I-002). Zero network.
    OllamaPolicy -- the opt-in real path (qwen3.8 over localhost:11434). The
                   SOLE module that MAY import a network client, and it does so
                   *lazily*, so `import coding_agent.policy` opens no socket
                   (K-06 / T-02 / I-009).

`resolve()` is the model-availability taxonomy (R-14 / E-11 / E-12):
    DEGRADED_MOCK -- daemon unreachable -> fall back to MockPolicy + banner, 0
    PULL_REQUIRED -- model not pulled  -> remediation string, exit 4
    RUN_REAL       -- model present     -> real OllamaPolicy, no banner, 0

It is resolved by an injectable `probe` (a callable returning
(reachable, model_present)) so the automated suite never needs Ollama; the real
probe lazy-imports httpx.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

# ---------------------------------------------------------------- C-02 / I-004


class Action:
    """Marker base for the closed `ToolCall | STOP | NOOP` tag-union (I-004)."""


@dataclass(frozen=True)
class ToolCall(Action):
    """A request to run one tool (routed through the permission layer)."""

    name: str
    args: dict = field(default_factory=dict)


@dataclass(frozen=True)
class STOP(Action):
    """The policy's *declaration* of completion.

    A bare STOP is only a promise: the run settles VERIFIED only if the verifier
    also returned VERIFIED (I-006 / C-08); otherwise it is a FAILED-with-promise
    and the loop continues or hits budget.
    """

    final_outcome: str = "VERIFIED"


@dataclass(frozen=True)
class NOOP(Action):
    """No tool requested this iteration; feeds STALLED/DENIED_LOOP detection."""

    note: str = ""


class UnrecognizedAction(Exception):
    """E-02 / I-004: a policy output that is not in the closed action space.

    Coerced to an ERROR-tagged action by the loop -- recorded on the iteration's
     `errors`, the loop continues to the next iteration, and K-08 consecutive
    ERROR iterations terminate `ERROR` -- never a silent no-op.
    """

    def __init__(self, value: object) -> None:
        self.value = value
        super().__init__(f"unrecognized action: {value!r}")


def coerce_action(x: object) -> Action:
    """Validate a policy output against the closed tag-union (I-004 / E-02).

    Passes a well-formed `ToolCall`/`STOP`/`NOOP` through unchanged; raises
     `UnrecognizedAction` for anything else (an unknown type, a raw string, a
    number, ...) so the loop records an explicit ERROR instead of swallowing it.
    """
    if isinstance(x, Action):
        return x
    raise UnrecognizedAction(x)


# ---------------------------------------------------------------- MockPolicy


@runtime_checkable
class Policy(Protocol):
    """C-02: the only interface a run uses to reach a policy (section 4 / R-02)."""

    def select(self, context: object, observation: object) -> list[Action]: ...


@dataclass
class MockPolicy:
    """A deterministic, offline double (C-02 / R-13 / K-06).

    `script` is the list of per-iteration *batches* (I-014: one action batch per
    iteration) the policy replays in order. Once `script` is exhausted, the policy
    returns a single `NOOP` so a never-verifying script stalls at the iterator cap
    rather than emitting a false `VERIFIED` (I-006).
    """

    script: list[list[Action]]
    _i: int = field(default=0, init=False, repr=False)

    def select(self, context: object = None, observation: object = None) -> list[Action]:
        if self._i < len(self.script):
            batch = list(self.script[self._i])
            self._i += 1
            return batch
        return [NOOP()]  # exhausted: stall, do NOT fabricate a VERIFIED

    def select_all(self) -> list[list[Action]]:
        """Return the full scripted batch sequence for byte-identical replay."""
        return [list(b) for b in self.script]

    @classmethod
    def rule_driven(cls, rules: list[list[Action]]) -> MockPolicy:
        """Alias for the same surface: a rule-driven arc is just a fixed script."""
        return cls(rules)


# ---------------------------------------------------------------- OllamaPolicy


@dataclass
class OllamaPolicy:
    """The opt-in real path (C-02 / R-15): qwen3.8 over localhost:11434.

    The SOLE module that MAY import a network client -- and it does so *lazily*
    inside `_client`, so `import coding_agent.policy` opens no socket (K-06). Its
     `select` is best-effort and is NEVER asserted by the offline suite (K-06).
    """

    model: str
    host: str = "http://localhost:11434"
    seed: int | None = None
    probe: Callable[[], tuple[bool, bool]] | None = field(default=None, repr=False)

    def select(self, context: object, observation: object) -> list[Action]:
        # Best-effort real generation. The client is imported lazily so the
        # offline suite never touches the network or even requires httpx.
        client = self._client()
        return client.select(self.model, self.host, self.seed, context, observation)

    def _client(self) -> Any:
        try:
            import httpx
        except ImportError:
            raise RuntimeError(
                "OllamaPolicy requires the optional '[agents-real]' extra "
                "(`uv pip install -e .[agents-real]`) to reach the model."
            )
        return httpx.Client(base_url=self.host.rstrip("/"), timeout=30.0)

    @classmethod
    def model_for(cls, model: str) -> OllamaPolicy:
        """Construct a policy for `model` without touching the network."""
        return cls(model=model)


# ---------------------------------------------------------------- R-14 taxonomy


class Availability(str, Enum):
    """The model-availability taxonomy resolved on `--real` (R-14 / E-11 / E-12)."""

    DEGRADED_MOCK = "DEGRADED_MOCK"
    PULL_REQUIRED = "PULL_REQUIRED"
    RUN_REAL = "RUN_REAL"


@dataclass(frozen=True)
class Resolution:
    """The outcome of resolving model availability (C-08 / R-14)."""

    availability: Availability
    policy: object
    banner: str | None = None
    exit_code: int = 0
    remediation: str | None = None


def resolve(probe: Callable[[], tuple[bool, bool]], *, model: str = "qwen3.8") -> Resolution:
    """Resolve model availability against an injectable `probe` (R-14).

    `probe` is a callable returning `(reachable: bool, model_present: bool)`:
        not reachable             -> DEGRADED_MOCK (fall back to MockPolicy, 0)
        reachable, model absent   -> PULL_REQUIRED (remediation string, exit 4)
        reachable, model present  -> RUN_REAL      (real OllamaPolicy, no banner, 0)
    """
    reachable, model_present = probe()
    if not reachable:
        banner = "DEGRADED_MOCK: Ollama daemon unreachable; running offline MockPolicy"
        return Resolution(
            availability=Availability.DEGRADED_MOCK,
            policy=MockPolicy([]),
            banner=banner,
            exit_code=0,
            remediation=None,
        )
    if not model_present:
        return Resolution(
            availability=Availability.PULL_REQUIRED,
            policy=MockPolicy([]),
            banner=None,
            exit_code=4,
            remediation=f"ollama pull {model}",
        )
    return Resolution(
        availability=Availability.RUN_REAL,
        policy=OllamaPolicy(model=model),
        banner=None,
        exit_code=0,
        remediation=None,
    )


__all__ = [
    "NOOP",
    "STOP",
    "Action",
    "Availability",
    "MockPolicy",
    "OllamaPolicy",
    "Policy",
    "Resolution",
    "ToolCall",
    "UnrecognizedAction",
    "coerce_action",
    "resolve",
]
