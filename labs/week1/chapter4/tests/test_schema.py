# pyright: reportMissingImports=false

import json

import pytest

from rag_eval.schema import SchemaError, load_json, load_yaml, validate_document


def test_eval_schema_rejects_missing_version():
    with pytest.raises(SchemaError):
        validate_document({"dataset_id": "x"}, "eval")


def test_load_json_validates_document(tmp_path):
    path = tmp_path / "labels.json"
    path.write_text(json.dumps({"q-1": {"correct": True}}))
    assert load_json(path, "labels")["q-1"]["correct"] is True


def test_load_yaml_validates_gates(tmp_path):
    path = tmp_path / "gates.yml"
    path.write_text("version: 1\ngates:\n  - metric: accuracy\n    constraint: drop\n    max_pct_points: 1.0\n")
    assert load_yaml(path, "gates")["version"] == 1


def test_invalid_yaml_is_schema_error(tmp_path):
    path = tmp_path / "gates.yml"
    path.write_text("version: [")
    with pytest.raises(SchemaError):
        load_yaml(path, "gates")
