"""T-08 & T-14 (SPEC section 9.3): the structured-output reliability boundary.

- T-08: the validate gate (I-009 / R-10): a conforming object validates; an
        out-of-range confidence, a missing field, and an extra property each fail;
        structured retries exhaust to ERROR and never to VALID.
- T-14: parse_json accepts both a fenced ```json ... ``` and bare JSON, routing
        both to the same schema; a non-JSON string returns (None, reason).
"""

import json

from model_playground.structured import (
    ANSWER_SCHEMA,
    DEFAULT_MAX_RETRIES,
    ValidationResult,
    build_retry_prompt,
    parse_and_validate,
    parse_json,
    validate,
)
from model_playground.types import Message, Role

OK = json.dumps({"answer": "yes", "confidence": 0.9, "reasoning_required": False})


# ---------------------------------------------------------------- T-08   / I-009
def test_t08a_conforming_object_validates_ok():
    vr = parse_and_validate(OK, ANSWER_SCHEMA)
    assert vr.ok is True
    assert vr.data == json.loads(OK)
    assert vr.errors == []
    assert vr.raw == OK


def test_t08b_out_of_range_confidence_fails():
    # 1.5 > maximum 1 => the object is syntactically valid but semantically not.
    vr = parse_and_validate(
        json.dumps({"answer": "x", "confidence": 1.5, "reasoning_required": True})
    )
    assert vr.ok is False
    assert any("confidence" in e for e in vr.errors)


def test_t08c_missing_required_field_fails():
    vr = parse_and_validate(json.dumps({"answer": "x", "confidence": 0.5}))
    assert vr.ok is False
    assert any("reasoning_required" in e for e in vr.errors)


def test_t08d_extra_property_fails_additional_properties_false():
    vr = parse_and_validate(
        json.dumps(
            {"answer": "x", "confidence": 0.5, "reasoning_required": True, "extra": 1}
        )
    )
    assert vr.ok is False


def test_t08e_empty_answer_string_fails_min_length():
    vr = parse_and_validate(
        json.dumps({"answer": "", "confidence": 0.5, "reasoning_required": False})
    )
    assert vr.ok is False


def test_t08_invalid_data_never_populated_as_valid():
    # Even when handed a data dict that is out-of-range, .data must be None.
    bad = {"answer": "x", "confidence": 2.0, "reasoning_required": True}
    vr = validate(bad, ANSWER_SCHEMA, raw="{}")
    assert vr.ok is False
    assert vr.data is None
    assert vr.raw == "{}"


def test_t08_f_is_none_data_is_not_ok():
    vr = validate(None, ANSWER_SCHEMA)
    assert vr is not None
    assert vr.ok is False


# ---------------------------------------------------------------- T-14   / E-11
def test_t14_fenced_json_parses():
    text = f"```json\n{OK}\n```"
    data, errors = parse_json(text)
    assert data == json.loads(OK)
    assert errors == []


def test_t14_bare_json_parses():
    data, errors = parse_json(OK)
    assert data == json.loads(OK)
    assert errors == []


def test_t14_fenced_and_bare_route_to_same_schema():
    # Both forms must validate via the same schema to the same verdict.
    assert parse_and_validate(f"```json\n{OK}\n```", ANSWER_SCHEMA).ok is True
    assert parse_and_validate(OK, ANSWER_SCHEMA).ok is True


def test_t14_non_json_returns_none_and_reason():
    data, errors = parse_json("this is not json at all")
    assert data is None
    assert len(errors) == 1
    assert "parse error" in errors[0]


def test_t14_bare_non_object_returns_none():
    # A JSON array parses as JSON but is not an object -> not accepted.
    data, errors = parse_json("[1, 2, 3]")
    assert data is None
    assert errors


# ---------------------------------------------------------------- retry prompt
def test_retry_prompt_carries_last_failure():
    last = ValidationResult(ok=False, data=None, errors=["confidence: too big"], raw=OK)
    msgs = build_retry_prompt([Message(Role.USER, "hi")], last)
    assert len(msgs) == 2
    assert "confidence" in msgs[-1].content
    assert msgs[-1].role == Role.SYSTEM.value


def test_default_max_retries_is_2():
    # K-03: default max_retries is 2.
    assert DEFAULT_MAX_RETRIES == 2
