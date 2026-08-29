# E-13 / R-19 / F-013 model-availability taxonomy. resolve_availability returns
# EXACTLY ONE of DEGRADED_MOCK / PULL_REQUIRED / RUN_REAL. Mock + unreachable cases
# are self-contained; reachable cases monkeypatch _probe so no real network is hit.
import dataclasses

from rag.availability import Availability, Outcome, resolve_availability


def test_mock_forces_degraded_mock():
    o = resolve_availability(["nomic-embed-text", "qwen3.8:27b-mlx"], mock=True)
    assert o.kind == Availability.DEGRADED_MOCK
    assert o.use_mock is True and o.exit_code == 0 and o.banner is not None


def test_unreachable_degrades_to_mock():
    o = resolve_availability(["x"], daemon_url="http://127.0.0.1:1", timeout=0.15)
    assert o.kind == Availability.DEGRADED_MOCK
    assert o.use_mock is True and o.exit_code == 0 and o.banner is not None


def test_pull_required(monkeypatch):
      # the stand-in accepts any args/kwargs -- resolve calls _probe(url, timeout=..)
    monkeypatch.setattr("rag.availability._probe", lambda *a, **k: (True, {"the-model"}))
    o = resolve_availability(["not-pulled", "the-model"], mock=False)
    assert o.kind == Availability.PULL_REQUIRED and o.exit_code == 4
    assert set(o.missing_models) == {"not-pulled"}
    assert o.banner and "ollama pull" in o.banner


def test_run_real(monkeypatch):
    monkeypatch.setattr("rag.availability._probe", lambda *a, **k: (True, {"the-model"}))
    o = resolve_availability(["the-model"], mock=False)
    assert o.kind == Availability.RUN_REAL and o.use_mock is False
    assert o.exit_code == 0 and o.banner is None


def test_outcome_is_a_dataclass_with_three_outcomes():
    assert dataclasses.is_dataclass(Outcome)
      # the three E-13 outcomes are mutually exclusive: exactly three enum members
    assert len(list(Availability)) == 3
    assert getattr(Outcome, "__dataclass_params__", None) is not None
