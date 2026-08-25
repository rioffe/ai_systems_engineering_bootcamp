"""T-09/T-10/T-11/T-13/T-15 (SPEC section 9.4): offscreen GUI tests.

The window is built with an injected mock registry so no network is touched
(E-12 / K-04). Qt runs offscreen (tests/conftest.py sets QT_QPA_PLATFORM).
"""

import time

import pytest
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication

from model_playground.registry import build_default_registry
from model_playground.ui import MainWindow


def _make_window():
    return MainWindow(registry=build_default_registry(), used_fallback=True)


def _select(window, ids):
    for mid, box in window._model_boxes.items():
        box.setChecked(mid in ids)
    window._validate()


def _drain(window, limit_s=10.0):
    """Block until no worker is live, then flush queued terminal signals."""
    app = QApplication.instance()
    end = time.perf_counter() + limit_s
    while time.perf_counter() < end:
        if not window.live_workers():
            for _ in range(30):
                app.processEvents()
                time.sleep(0.001)
            return
        app.processEvents()
        time.sleep(0.005)
    raise AssertionError("timed out draining workers")


@pytest.fixture
def window(qtbot):
    w = _make_window()
    w.show()
    return w


# ---------------------------------------------------------------- T-15    / E-01
def test_t15_empty_prompt_disables_run(window):
    window.prompt.setPlainText("")
    assert window._validate() is False
    assert window.btn_run.isEnabled() is False
    assert window.lbl_message.text() == "Prompt must not be empty"


def test_t15_no_model_selected_disables_run(window):
    window.prompt.setPlainText("a prompt")
    for box in window._model_boxes.values():
        box.setChecked(False)
    assert window._validate() is False
    assert window.btn_run.isEnabled() is False
    assert window.lbl_message.text() == "Select at least one model"


def test_t15_bad_seed_disables_run(window):
    window.prompt.setPlainText("a prompt")
    window.edit_seed.setText("not-an-integer")
    assert window._validate() is False
    assert window.lbl_message.text() == "Seed must be an integer or blank"


def test_t15_valid_config_enables_run(window):
    window.prompt.setPlainText("a valid prompt")
    _select(window, {"mock/fast"})
    assert window._validate() is True
    assert window.btn_run.isEnabled() is True
    assert window.lbl_message.text() == ""


# ---------------------------------------------------------------- T-13    / state machine
def test_t13_state_machine_idle_run_settle(window, qtbot):
    assert window.current_state() == "IDLE"
    assert window.btn_cancel.isEnabled() is False
    window.prompt.setPlainText("compare the two models on this prompt")
    _select(window, {"mock/fast"})
    window.on_run()
    assert window.current_state() == "RUNNING"
    assert window.btn_run.isEnabled() is False
    assert window.btn_cancel.isEnabled() is True
    assert len(window.live_workers()) == 1
    _drain(window)
    assert window.current_state() == "IDLE"
    assert window.btn_cancel.isEnabled() is False
    assert window.live_workers() == []
    assert window.panels()["mock/fast"].metrics.status == "COMPLETED"
    assert window.btn_run.isEnabled() is True


def test_t13_cancel_returns_to_idle_with_terminal_panels(window, qtbot):
    window.prompt.setPlainText("run then cancel")
    _select(window, {"mock/fast", "mock/slow"})
    window.on_run()
    time.sleep(0.15)  # let the slow mock get into STREAMING first
    window.on_cancel()
    _drain(window)
    assert window.current_state() == "IDLE"
    assert window.live_workers() == []
    for panel in window.panels().values():
        assert panel.metrics is not None
        assert panel.done is True


# ---------------------------------------------------------------- T-10    / E-02, K-02
def test_t10_isolated_failure_siblings_continue(window, qtbot):
    window.prompt.setPlainText("one succeeds, one fails mid-stream")
    window.chk_structured.setChecked(False)
    window.chk_stream.setChecked(True)
    _select(window, {"mock/fast", "mock/raising"})
    window.on_run()
    _drain(window)
    fast = window.panels()["mock/fast"].metrics
    raising = window.panels()["mock/raising"].metrics
    assert fast is not None
    assert fast.status == "COMPLETED"
    assert raising.status == "ERROR"
    assert raising.error and "mid-stream" in raising.error
    assert all(p.done for p in window.panels().values())
    assert window.live_workers() == []


# ---------------------------------------------------------------- T-09    / I-010, E-12
def test_t09_cancel_leaves_no_live_workers(window, qtbot):
    window.prompt.setPlainText("cancel demo")
    _select(window, {"mock/fast", "mock/slow"})
    window.on_run()
    time.sleep(0.15)
    window.on_cancel()
    _drain(window)
    assert window.live_workers() == []
    assert all(p.done for p in window.panels().values())


def test_t09_new_run_cancels_prior(window, qtbot):
    window.prompt.setPlainText("duplicate run demo")
    window.chk_structured.setChecked(False)
    window.chk_stream.setChecked(True)
    _select(window, {"mock/fast"})
    window.on_run()
    assert len(window.live_workers()) == 1
    window.on_run()  # E-12: a second run cancels the first, one new run
    assert len(window.live_workers()) == 1
    _drain(window)
    assert window.live_workers() == []


# ---------------------------------------------------------------- T-11    / I-011, K-01
def test_t11_off_thread_and_liveness(window, qtbot):
    import threading

    window.prompt.setPlainText("liveness off-thread check")
    window.chk_structured.setChecked(False)
    window.chk_stream.setChecked(True)
    _select(window, {"mock/slow"})
    window.on_run()

    main_tid = threading.get_ident()
    qapp = QApplication.instance()
    wtids = set()
    end = time.perf_counter() + 3.0
    while time.perf_counter() < end and not wtids:
        for w in window.live_workers():
            if w.thread_id is not None:
                wtids.add((w, w.thread_id))
        qapp.processEvents()
        time.sleep(0.002)
    assert wtids, "no worker thread id observed"
    for _w, tid in wtids:
        assert tid != main_tid  # I-011: inference off the UI thread

        # K-01: the event loop is still serviced while a model streams.
    latencies = []

    def probe():
        latencies.append((time.perf_counter() - fire) * 1000.0)

    fire = time.perf_counter()
    QTimer.singleShot(5, probe)
    for _ in range(200):
        qapp.processEvents()
        time.sleep(0.002)
        if latencies:
            break
    assert latencies, "event loop never serviced a posted task during the run"
    assert max(latencies) < 100.0  # generous bound; K-01 target is p95 < 50 ms
    _drain(window)
