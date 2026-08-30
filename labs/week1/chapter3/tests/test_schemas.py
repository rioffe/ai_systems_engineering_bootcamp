"""Tests for rag.schemas -- T-08: the JSON-Schema gate (I-010 / R-09 / R-10).

The gate must ACCEPT a well-formed answer/verdict and REJECT an out-of-range
confidence, a missing required field, an unknown field, a bad status enum, and a
non-array list field -- under whichever path is live (real jsonschema or the
offline structural validator).
"""

from __future__ import annotations

import json

import pytest

from rag.schemas import (
    SchemaError,
    answer_schema,
    emit,
    using_jsonschema,
    validate_answer,
    validate_verdict,
    verdict_schema,
)
from rag.types import Answer, Verdict


def _valid_answer() -> dict:
    return {
        "q_id": "q1",
        "text": "ok",
        "confidence": 0.7,
        "citations": [],
        "error": None,
        "status": "COMPLETED",
    }


def _valid_verdict() -> dict:
    return {
        "q_id": "q1",
        "status": "JUDGED",
        "unsupported_claims": [],
        "faithfulness": 1.0,
        "completeness": 1.0,
        "citation_quality": 1.0,
    }


def test_valid_answer_and_verdict_pass():
    validate_answer(_valid_answer())
    validate_verdict(_valid_verdict())


def test_dataclass_objects_validate():
    validate_answer(Answer(q_id="q1", text="ok", confidence=0.5, status="COMPLETED"))
    validate_verdict(Verdict(q_id="q1", status="JUDGED"))


def test_out_of_range_confidence_rejected():
    bad = _valid_answer()
    bad["confidence"] = 1.5
    with pytest.raises(SchemaError):
        validate_answer(bad)


def test_missing_required_field_rejected():
    bad = _valid_answer()
    del bad["text"]
    with pytest.raises(SchemaError):
        validate_answer(bad)


def test_unknown_field_rejected():
    bad = _valid_answer()
    bad["sneaky"] = 1
    with pytest.raises(SchemaError):
        validate_answer(bad)


def test_malformed_verdict_rejected():
    bad = _valid_verdict()
    bad["status"] = "MAYBE"
    with pytest.raises(SchemaError):
        validate_verdict(bad)


def test_verdict_non_array_rejected():
    bad = _valid_verdict()
    bad["unsupported_claims"] = 5
    with pytest.raises(SchemaError):
        validate_verdict(bad)


def test_emit_validates_then_writes(tmp_path):
    p = emit(str(tmp_path), "answer", _valid_answer())
    with open(p, encoding="utf-8") as fh:
        loaded = json.load(fh)
    assert loaded["q_id"] == "q1"
    with pytest.raises(SchemaError):
        emit(str(tmp_path), "answer", {**_valid_answer(), "confidence": 2.0})


def test_schemas_have_required_shape():
    a = answer_schema()
    v = verdict_schema()
    assert set(a["required"]) == {"q_id", "text", "confidence", "status"}
    assert a.get("additionalProperties") is False
    assert v["properties"]["status"]["enum"] == ["JUDGED", "ERROR", "SKIPPED"]
    assert using_jsonschema() in (True, False)


def test_jsonschema_or_structural_both_enforce():
    with pytest.raises(SchemaError):
        validate_answer({**_valid_answer(), "confidence": 5.0})


def test_verdict_metric_out_of_range_rejected():
    bad = _valid_verdict()
    bad["faithfulness"] = 100.0
    with pytest.raises(SchemaError):
        validate_verdict(bad)
