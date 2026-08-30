# pyright: reportMissingImports=false

import json

import pytest

from rag_eval.report import load_artifact, render_compare_table, write_eval_artifact


def artifact():
    return {"eval_report_version": "0.1", "dataset_id": "x", "usage_kind": "synthetic", "cases": [], "aggregate": {"by_category": {}, "accuracy": 0.5}}


def test_eval_artifact_is_canonical_and_loadable(tmp_path):
    path = tmp_path / "eval.json"
    write_eval_artifact(path, artifact())
    assert load_artifact(path, "eval")["eval_report_version"] == "0.1"
    assert json.loads(path.read_text())["dataset_id"] == "x"


def test_bad_artifact_is_rejected(tmp_path):
    path = tmp_path / "bad.json"
    # pi-lens-ignore: python-path-traversal
    path.write_text(json.dumps({"dataset_id": "x"}))
    with pytest.raises(ValueError):
        load_artifact(path, "eval")


def test_compare_table_renders_missing_marker():
    assert "n/m" in render_compare_table({"metrics": {"accuracy": {"baseline": "n/m", "current": "n/m", "delta": "n/m"}}})
