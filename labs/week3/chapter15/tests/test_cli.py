"""R-16 / K-01/K-02 / T-01 / T-08 / T-09 / T-10 / T-12: CLI surface."""
import json
from pathlib import Path

from coding_agent.cli import main


def fixture_repo():
    return str(Path(__file__).parents[1] / "fixtures" / "parse-config")


def test_run_good_fixture_emits_verified_trajectory(tmp_path):
    out = tmp_path / "trajectory.json"
    sandbox = tmp_path / "sandbox"
    code = main(["run", "--task", "parse config", "--repo", fixture_repo(),
                 "--mock", "--sandbox", str(sandbox), "--out", str(out)])
    assert code == 0
    doc = json.loads(out.read_text())
    assert doc["final_outcome"] == "VERIFIED"
    assert doc["iterations_used"] == 1
    assert not sandbox.exists()


def test_experiment_emits_pinned_arc(tmp_path):
    out = tmp_path / "experiment.json"
    code = main(["experiment", "--task", "parse-config", "--repo", fixture_repo(),
                 "--mock", "--sandbox", str(tmp_path / "sbx"), "--out", str(out)])
    assert code == 0
    doc = json.loads(out.read_text())
    assert doc["iterations_to_verified"] == 3
    assert {p["phase"]: p["iteration"] for p in doc["phases"]} == {
        "detect": 1, "diagnose": 2, "repair": 3
    }


def test_inspect_and_compare_are_offline(tmp_path, capsys):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    for out in (a, b):
        assert main(["run", "--task", "parse config", "--repo", fixture_repo(),
                     "--mock", "--sandbox", str(tmp_path / out.stem), "--out", str(out)]) == 0
    assert main(["inspect", "--in", str(a)]) == 0
    assert "VERIFIED" in capsys.readouterr().out
    report = tmp_path / "compare.json"
    assert main(["compare", "--baseline", str(a), "--current", str(b),
                 "--out", str(report)]) == 0
    assert json.loads(report.read_text())["regression"] is False


def test_usage_errors_return_two(tmp_path):
    assert main([]) == 2
    assert main(["run", "--task", "", "--repo", fixture_repo(), "--out", str(tmp_path / "x")]) == 2
    assert main(["run", "--task", "x", "--repo", fixture_repo(), "--max-iterations", "0",
                 "--out", str(tmp_path / "x")]) == 2


def test_bad_artifact_returns_three(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    assert main(["inspect", "--in", str(bad)]) == 3


def test_own_source_repo_is_refused(tmp_path):
    from coding_agent import sandbox
    out = tmp_path / "x.json"
    assert main(["run", "--task", "x", "--repo", sandbox.own_source_root(),
                 "--out", str(out)]) == 2
    assert not out.exists()


def test_real_down_degrades_to_mock(tmp_path, monkeypatch):
    from coding_agent import cli
    monkeypatch.setattr(cli, "_probe_ollama", lambda host, model: (False, False))
    out = tmp_path / "trajectory.json"
    code = main(["run", "--task", "parse config", "--repo", fixture_repo(),
                 "--real", "--sandbox", str(tmp_path / "sbx"), "--out", str(out)])
    assert code == 0
    doc = json.loads(out.read_text())
    assert doc["policy"] == "mock"
    assert doc["availability_banner"]


def test_real_missing_model_returns_four(tmp_path, monkeypatch):
    from coding_agent import cli
    monkeypatch.setattr(cli, "_probe_ollama", lambda host, model: (True, False))
    assert main(["run", "--task", "parse config", "--repo", fixture_repo(),
                 "--real", "--out", str(tmp_path / "x.json")]) == 4
