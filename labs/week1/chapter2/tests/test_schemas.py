"""T-08 / T-14 -- the structured-output reliability boundary (ch1 C-05 analog).

T-08 (I-010): the answer and verdict schemas reject a syntactically-valid-but-out-of-
schema object: an out-of-range ``confidence``, a missing required field, and an extra
property each fail; and the error-informed retry loop exhausts to a terminal non-ok
result (never a fabricated/invalid object reaching status "COMPLETED"/"JUDGED").
T-14: ``parse_json`` accepts both a fenced ```json ... ``` and bare JSON, routing both
to the same schema; a non-JSON string returns ``(None, [reason])``.
"""

import json

import pytest

from rag_eval.schemas import (
    ANSWER_SCHEMA,
    DEFAULT_MAX_RETRIES,
    VERDICT_SCHEMA,
    build_retry_directive,
    generate_structured,
    parse_and_validate,
    parse_json,
    validate,
)

GOOD_ANSWER = json.dumps(
    {"answer": "42 dollars", "confidence": 0.9, "sources": ["001"]}
)
GOOD_VERDICT = json.dumps(
    {
        "correct": True,
        "supported": True,
        "complete": True,
        "unsupported_claims": [],
        "total_factual_claims": 3,
        "rationale": "all claims grounded",
    }
)


# ---------------------------------------------------------------- T-08 -- schema gate
def test_t08_answer_conforming_object_validates():
    vr = parse_and_validate(GOOD_ANSWER, ANSWER_SCHEMA)
    assert vr.ok and vr.data == json.loads(GOOD_ANSWER) and vr.errors == []


def test_t08_out_of_range_confidence_fails():
    # 1.5 is syntactically valid but > maximum 1.
    vr = parse_and_validate(
        json.dumps({"answer": "x", "confidence": 1.5, "sources": []}), ANSWER_SCHEMA
    )
    assert not vr.ok
    assert any("confidence" in e for e in vr.errors)


def test_t08_missing_required_field_fails():
    vr = parse_and_validate(
        json.dumps({"answer": "x", "confidence": 0.5}), ANSWER_SCHEMA
    )
    assert not vr.ok
    assert any("sources" in e for e in vr.errors)


def test_t08_empty_answer_min_length_fails():
    vr = parse_and_validate(
        json.dumps({"answer": "", "confidence": 0.5, "sources": []}), ANSWER_SCHEMA
    )
    assert not vr.ok


def test_t08_extra_property_fails_additional_properties_false():
    vr = parse_and_validate(
        json.dumps({"answer": "x", "confidence": 0.5, "sources": [], "extra": 1}),
        ANSWER_SCHEMA,
    )
    assert not vr.ok


def test_t08_invalid_data_never_populated_as_valid():
    vr = validate(
        {"answer": "x", "confidence": 2.0, "sources": []}, ANSWER_SCHEMA, raw="{}"
    )
    assert not vr.ok and vr.data is None and vr.raw == "{}"


def test_t08_verdict_schema_rejects_malformed():
    # Missing required fields -> not "JUDGED"-eligible.
    vr = parse_and_validate(json.dumps({"correct": True}), VERDICT_SCHEMA)
    assert not vr.ok
    vr2 = parse_and_validate(GOOD_VERDICT, VERDICT_SCHEMA)
    assert vr2.ok


# ---------------------------------------------------------------- T-08 -- retry loop
def test_t08_retry_exhausts_to_error_never_fabricates():
    # The "model" always returns bad JSON; after max_retries the loop gives up.
    def always_bad(_attempt, _last):
        return "not json"

    res = generate_structured(
        always_bad, ANSWER_SCHEMA, max_retries=DEFAULT_MAX_RETRIES
    )
    assert res.ok is False
    assert res.data is None
    assert res.attempts == DEFAULT_MAX_RETRIES + 1  # 1 initial + 2 retries
    assert res.last is not None and not res.last.ok


def test_t08_retry_recovers_on_later_attempt():
    # Bad on attempts 0,1; valid on attempt 2 -> ok, using only the valid one.
    def flaky(attempt, _last):
        return "not json" if attempt < 2 else GOOD_ANSWER

    res = generate_structured(flaky, ANSWER_SCHEMA, max_retries=DEFAULT_MAX_RETRIES)
    assert res.ok is True and res.attempts == 3 and res.data == json.loads(GOOD_ANSWER)


def test_t08_retry_directive_carries_last_failure():
    from rag_eval.schemas import ValidationResult

    last = ValidationResult(ok=False, data=None, errors=["confidence: too big"], raw="")
    directive = build_retry_directive(ANSWER_SCHEMA, last)
    assert "confidence" in directive
    assert "answer" in directive and "sources" in directive


# ---------------------------------------------------------------- T-14 -- parse forms
def test_t14_fenced_json_parses():
    data, errors = parse_json(f"```json\n{GOOD_ANSWER}\n```")
    assert data == json.loads(GOOD_ANSWER) and errors == []


def test_t14_bare_json_parses():
    data, errors = parse_json(GOOD_ANSWER)
    assert data == json.loads(GOOD_ANSWER) and errors == []


def test_t14_fenced_and_bare_route_to_same_schema():
    fenced = parse_and_validate(f"```json\n{GOOD_ANSWER}\n```", ANSWER_SCHEMA)
    bare = parse_and_validate(GOOD_ANSWER, ANSWER_SCHEMA)
    assert fenced.ok and bare.ok and fenced.data == bare.data


def test_t14_non_json_returns_none_and_reason():
    data, errors = parse_json("this is not json at all")
    assert data is None and len(errors) == 1 and "parse" in errors[0]


def test_t14_bare_non_object_returns_none():
    data, errors = parse_json("[1, 2, 3]")
    assert data is None and errors
