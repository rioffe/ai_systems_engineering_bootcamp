"""Worker-level structured-pipeline coverage (R-11 / E-03 / T-08e).

Verifies that an always-invalid structured output exhausts `max_retries` and
reaches a terminal ERROR (never VALID), exercising the retry/fallback path of
the reliability boundary. Runs offscreen, no network.
"""

import os
import time

from PyQt5.QtCore import QCoreApplication

from model_playground.model import MockModel
from model_playground.registry import ModelRegistry, ModelSpec
from model_playground.structured import ANSWER_SCHEMA, DEFAULT_MAX_RETRIES
from model_playground.types import Message, Role
from model_playground.worker import RunWorker

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _registry_with(spec: ModelSpec) -> ModelRegistry:
    reg = ModelRegistry()
    reg.register(spec)
    return reg


def test_structured_always_invalid_exhausts_retries_to_error():
    # MockModel emits plain tokens, never schema-valid JSON: with retry
    # allowed, the worker must exhaust retries and settle to ERROR (not VALID).
    app = QCoreApplication.instance() or QCoreApplication([])
    spec = ModelSpec(MockModel("mock/fast", "fast"))
    reg = _registry_with(spec)

    got = {}
    worker = RunWorker(
        spec.model,
        spec.model.model_id,
        reg,
        schema=ANSWER_SCHEMA,
        structured_mode=True,
        streaming=False,
        max_retries=DEFAULT_MAX_RETRIES,
        timeout_s=5.0,
    )
    worker.structured.connect(lambda mid, vr: got.setdefault("vr", vr))
    worker.metrics_ready.connect(lambda mid, m: got.setdefault("m", m))

    worker.start_run(
        [Message(Role.USER, "answer in json please")],
        {"temperature": 0.0, "seed": 42},
    )
    end = time.perf_counter() + 5.0
    while time.perf_counter() < end and "m" not in got:
        app.processEvents()
        time.sleep(0.002)

    assert "m" in got, "worker never emitted a terminal metrics"
    m = got["m"]
    sr = got.get("vr")
    assert m.status == "ERROR"
    assert m.retries == DEFAULT_MAX_RETRIES  # all retries were attempted
    # I-009: we never accepted an unvalidated object as VALID.
    assert m.status != "VALID"
    assert sr is not None and sr.ok is False
