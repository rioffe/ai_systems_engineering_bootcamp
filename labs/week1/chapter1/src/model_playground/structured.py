"""C-05 structured output (SPEC section 4 / C-05): the reliability boundary.

Pipeline: raw text -> strip a single optional code fence -> json.loads ->
jsonschema.validate -> accept/reject. Every step is total: a failure yields a
structured reason and never an exception, and a validated object exists only when
the schema accepts it (I-009: never accept a valid-looking artifact as valid).
"""

from __future__ import annotations

import json
import re

from jsonschema import Draft202012Validator

from .types import Message, Role

# The default "answer" schema of chapter section 15 (fixed for v0.1, Q-01).
ANSWER_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["answer", "confidence", "reasoning_required"],
    "properties": {
        "answer": {"type": "string", "minLength": 1},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reasoning_required": {"type": "boolean"},
    },
}

# K-03 defaults.
DEFAULT_MAX_RETRIES = 2
DEFAULT_TIMEOUT_S = 30.0
# Matches a single ```json ... ``` (or bare ```...```) fence. E-11.
_FENCE = re.compile(r"^```(?:json)?[ \t]*\n?(.*?)\n?```$", re.DOTALL)


class ValidationResult:
    ok: bool
    data: dict | None
    errors: list[str]
    raw: str

    def __init__(
        self, ok: bool, data: dict | None, errors: list[str], raw: str
    ) -> None:
        self.ok = ok
        self.data = data
        self.errors = errors
        self.raw = raw

    def __repr__(self) -> str:
        return f"ValidationResult(ok={self.ok!r}, errors={self.errors!r}, raw={self.raw!r})"


def parse_json(text: str):
    # Strip one optional ```json``` fence, then json.loads (E-11). Bare JSON is
    # also accepted. Returns (data, errors); on any failure (None, [reason]);
    # never raises.
    stripped = (text or "").strip()
    matched = _FENCE.match(stripped)
    candidate = matched.group(1).strip() if matched else stripped
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as exc:
        return None, [f"json parse error: {exc}"]
    if not isinstance(data, dict):
        return None, [f"expected a JSON object, got {type(data).__name__}"]
    return data, []


def validate(data, schema: dict = ANSWER_SCHEMA, raw: str = "") -> ValidationResult:
    # Validate `data` against `schema`, collecting every error (I-009). Never raises.
    if data is None:
        return ValidationResult(False, None, ["parse failed: no JSON object"], raw)
    validator = Draft202012Validator(schema)
    errors: list[str] = []
    for err in validator.iter_errors(data):
        location = "/".join(str(p) for p in err.path) or "<root>"
        errors.append(f"{location}: {err.message}")
    ok = not errors
    return ValidationResult(ok, data if ok else None, errors, raw)


def parse_and_validate(raw_text: str, schema: dict = ANSWER_SCHEMA) -> ValidationResult:
    # Full raw -> parse -> validate pipeline, returning a ValidationResult.
    data, errors = parse_json(raw_text)
    if data is None:
        return ValidationResult(False, None, errors, raw_text)
    return validate(data, schema, raw=raw_text)


def build_retry_prompt(
    messages: list[Message], last: ValidationResult
) -> list[Message]:
    # An error-informed prompt for a structured re-attempt (E-03). Retries apply
    # only to the structured pipeline; plain-text mode has none (Q-06).
    reasons = "; ".join(last.errors) or "the output did not validate"
    directive = (
        "The previous response could not be validated: "
        + reasons
        + ". Respond with a single valid JSON object (no prose, no markdown "
        + 'fences) matching the schema: {"answer": <non-empty string>, '
        + '"confidence": <number in 0..1>, "reasoning_required": <boolean>}.'
    )
    return list(messages) + [Message(Role.SYSTEM, directive)]


__all__ = [
    "ANSWER_SCHEMA",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_TIMEOUT_S",
    "ValidationResult",
    "build_retry_prompt",
    "parse_and_validate",
    "parse_json",
    "validate",
]
