"""C-05 / C-06 structured-output gate (SPEC §4, ch1 C-05 analog) -- the reliability boundary.

The LLM and the judge must each emit a **structured** object: an answer
(``{answer, confidence, sources}`` per C-04 / §19) and a verdict
(``{correct, supported, complete, unsupported_claims, total_factual_claims, rationale}``
per C-06 / §19/§20). Both are gate-validated the ch1 way:

    raw text -> strip an optional ```json fence -> json.loads -> jsonschema.validate
     -> accept  OR  reject-with-retry.

Every step is total: a failure yields a structured ``ValidationResult`` and *never* an
exception, and a validated object exists only when the schema accepts it (I-010: we never
accept a valid-looking artifact as valid). The two schemas are embedded here as the single
source of truth and mirrored to ``schemas/answer.json`` / ``schemas/verdict.json`` (a
test-suite keeps them in sync by asserting equality).

``generate_structured`` runs the parse -> validate -> error-informed-retry loop
(SPEC §3.1, E-07/E-10) on top of a caller-supplied prompt function, so the model and judge
retry machinery is shared and the deterministic boundary rejects, never fabricates.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass

from jsonschema import Draft202012Validator

# C-05 / §19 answer schema (additionalProperties:false; T-08 pins the gates).
ANSWER_SCHEMA: dict = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "RAG grounded answer (SPEC C-04 / C-05, §19)",
    "type": "object",
    "additionalProperties": False,
    "required": ["answer", "confidence", "sources"],
    "properties": {
        "answer": {"type": "string", "minLength": 1},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "sources": {"type": "array", "items": {"type": "string"}},
    },
}

# C-06 / §19/§20 verdict schema (additionalProperties:false; T-08 pins the gates).
VERDICT_SCHEMA: dict = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "RAG judge verdict (SPEC C-04 / C-06, §19 / §20)",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "correct",
        "supported",
        "complete",
        "unsupported_claims",
        "total_factual_claims",
        "rationale",
    ],
    "properties": {
        "correct": {"type": "boolean"},
        "supported": {"type": "boolean"},
        "complete": {"type": "boolean"},
        "unsupported_claims": {"type": "array", "items": {"type": "string"}},
        "total_factual_claims": {"type": "integer", "minimum": 0},
        "rationale": {"type": "string"},
    },
}

# K-03 default. The retry budget: attempts = 1 initial + max_retries.
DEFAULT_MAX_RETRIES = 2

# Matches a single ```json ... ``` (or bare ```...```) fence (E-11 / ch1 E-11).
_FENCE = re.compile(r"^```(?:json)?[ \t]*\n?(.*?)\n?```$", re.DOTALL)


class ValidationResult:
    """The outcome of a parse+validate attempt (ch1 C-05).

    ``ok`` is True iff ``data`` is a schema-conforming object; ``errors`` lists every
    schema violation (empty when ok); ``raw`` is the original text for diagnostics.
    """

    __slots__ = ("ok", "data", "errors", "raw")

    def __init__(
        self, ok: bool, data: dict | None, errors: list, raw: str
    ) -> None:
        self.ok: bool = ok
        self.data: dict | None = data
        self.errors: list[str] = errors
        self.raw: str = raw

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"ValidationResult(ok={self.ok!r}, errors={self.errors!r}, raw={self.raw!r})"


def parse_json(text: str) -> tuple[dict | None, list[str]]:
    # Strip one optional fence, then json.loads (E-11 / ch1 E-11). Bare JSON is also
    # accepted. Returns (data, errors); on any failure (None, [reason]); never raises.
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


def validate(data: dict | None, schema: dict, raw: str = "") -> ValidationResult:
    # Validate `data` against `schema`, collecting every error (I-010). Never raises.
    if data is None:
        return ValidationResult(False, None, ["parse failed: no JSON object"], raw)
    validator = Draft202012Validator(schema)
    errors: list[str] = []
    for err in sorted(
        validator.iter_errors(data), key=lambda e: (list(e.path), e.message)
    ):
        location = "/".join(str(p) for p in err.path) or "<root>"
        errors.append(f"{location}: {err.message}")
    ok = not errors
    return ValidationResult(ok, data if ok else None, errors, raw)


def parse_and_validate(
    raw_text: str,
    schema: dict,
    raw_for_result: str | None = None,
) -> ValidationResult:
    # Full raw -> parse -> validate pipeline, returning a ValidationResult.
    result_raw = raw_for_result if raw_for_result is not None else raw_text
    data, errors = parse_json(raw_text)
    if data is None:
        return ValidationResult(False, None, errors, result_raw)
    return validate(data, schema, raw=result_raw)


def build_retry_directive(schema: dict, last: ValidationResult) -> str:
    # An error-informed directive for a structured re-attempt (SPEC §3.1 / ch1 E-03).
    # Appended to the system prompt on each retry so the model corrects the last failure.
    reasons = "; ".join(last.errors) or "the output did not validate"
    fields = ", ".join(schema.get("required", []))
    return (
        f"The previous response could not be validated: {reasons}. "
        f"Respond with a single valid JSON object (no prose, no markdown fences) matching "
        f"the schema whose required fields are: {fields}."
    )


@dataclass
class StructuredResult:
    """The terminal outcome of a ``generate_structured`` attempt loop."""

    ok: bool
    data: dict | None  # the validated object, or None
    last: ValidationResult  # the final attempt (carries the failing result on failure)
    attempts: int  # attempts made: 1 initial + retries


def generate_structured(
    prompt_for_attempt: Callable[[int, ValidationResult | None], str],
    schema: dict,
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> StructuredResult:
    # SPEC §3.1 / E-07 / E-10: parse -> validate, retrying up to `max_retries` with the
    # last error informed in the next `prompt_for_attempt(attempt_index, last_result)`.
    # On exhaustion the final failing result is returned (never a fabricated object).
    last: ValidationResult | None = None
    attempts = max_retries + 1
    for attempt in range(attempts):
        raw = prompt_for_attempt(attempt, last)
        result = parse_and_validate(raw, schema, raw_for_result=raw)
        last = result
        if result.ok:
            return StructuredResult(True, result.data, result, attempt + 1)
    assert last is not None  # loop ran at least once, so `last` is set
    return StructuredResult(False, None, last, attempts)


__all__ = [
    "ANSWER_SCHEMA",
    "DEFAULT_MAX_RETRIES",
    "StructuredResult",
    "ValidationResult",
    "VERDICT_SCHEMA",
    "build_retry_directive",
    "generate_structured",
    "parse_and_validate",
    "parse_json",
    "validate",
]
