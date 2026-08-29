"""Tests for rag.app -- the section-5.1 CLI exit-code contract (R-14 / R-15)."""

from __future__ import annotations

import json

from rag.app import main


def _gen(tmp):
    main(["gen-corpus", "--dir", tmp, "--n-docs", "8", "--n-questions", "5", "--seed", "7", "--quiet"])


def test_eval_emits_report(tmp_path):
    _gen(str(tmp_path))
    out = str(tmp_path / "out.json")
    rc = main(["eval", "--corpus", str(tmp_path / "documents"), "--dataset", str(tmp_path / "questions.json"), "--out", out, "--mock", "on", "--quiet"])
    assert rc == 0
    report = json.loads((tmp_path / "out.json").read_text())
    assert report["n_cases"] >= 1
    assert report["rows"]
    assert "by_tier" in report["aggregate"]


def test_happy_path_exit_zero(tmp_path):
    _gen(str(tmp_path))
    rc = main(["eval", "--corpus", str(tmp_path / "documents"), "--dataset", str(tmp_path / "questions.json"), "--out", str(tmp_path / "out.json"), "--mock", "on", "--quiet"])
    assert rc == 0


def test_e15_topn_lt_k_exit_two():
    rc = main(["eval", "--k", "10", "--top-n", "5", "--mock", "on", "--quiet"])
    assert rc == 2


def test_load_failure_exit_three():
    rc = main(["eval", "--corpus", "/nonexistent-corporus-xyz", "--mock", "on", "--quiet", "--out", "/dev/null"])
    assert rc == 3


def test_unknown_command_errors_out():
    try:
        main(["does-not-exist"])
    except SystemExit as e:
        assert e.code == 2
    else:
        raise AssertionError("expected SystemExit for an unknown subcommand")
