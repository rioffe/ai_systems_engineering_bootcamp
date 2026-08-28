"""Offscreen GUI acceptance tests (SPEC 9.3: T-08, T-13, T-14, T-15).

The Qt offscreen platform is used so these run with no display (E-11).
GUI drives use batch == N (a single emission per run) so the final label is
deterministic rather than timing dependent.
"""

from __future__ import annotations

import numpy as np
import pytest

from monte_carlo_pi.ui import MAIN_WINDOW_AVAILABLE, MAX_SCATTER_POINTS, MainWindow
from monte_carlo_pi.worker import Progress

if not MAIN_WINDOW_AVAILABLE:
    pytestmark = pytest.mark.skip(reason="PyQt5/Qt unavailable in this environment")


@pytest.fixture
def window(qtbot):
    w = MainWindow()
    w.show()
    return w


def _drive(window, qtbot, n, batch, interval_ms=0, seed=None, timeout_ms=20_000):
    window.spin_n.setValue(int(n))
    window.spin_batch.setValue(int(batch))
    window.spin_interval.setValue(int(interval_ms))
    window.edit_seed.setText(str(seed) if seed is not None else "")
    window.on_start()
    worker = window._worker
    qtbot.waitSignal(worker.completed, timeout=timeout_ms)  # nested loop dispatches
    qtbot.wait(50)  # flush any trailing signal
    return worker


# T-13: state machine IDLE -> RUNNING -> COMPLETED
def test_t13_state_machine_smoke(window, qtbot):
    _drive(window, qtbot, n=1000, batch=1000, interval_ms=0, seed=42)
    assert window.lbl_state.text() == "state: COMPLETED"
    assert "pi_hat:" in window.lbl_estimate.text()
    assert "std err:" in window.lbl_se.text()
    window.close()


def test_t13b_reset_returns_to_idle(window, qtbot):
    _drive(window, qtbot, n=1000, batch=1000, interval_ms=0, seed=42)
    window.on_reset()
    assert window.lbl_state.text() == "state: IDLE"
    assert window._worker is None  # E-06: reset stops the worker
    window.close()


# T-14: fixed seed reproduces the estimate through the UI
def test_t14_reproduces_with_fixed_seed(window, qtbot):
    window.spin_interval.setValue(0)
    n = 20_000
    _drive(window, qtbot, n=n, batch=n, seed=7)  # single emission -> deterministic
    first = window.lbl_estimate.text()
    window.on_reset()
    _drive(window, qtbot, n=n, batch=n, seed=7)
    second = window.lbl_estimate.text()
    assert first == second  # identical seed -> identical estimate
    window.close()


# T-15: inline validation controls the Start button (E-01)
def test_t15_validation_disables_start(window):
    window.spin_n.setValue(1_000_000)
    window.edit_seed.setText("not-an-integer")
    assert window._validate() is False
    assert window.btn_start.isEnabled() is False
    window.edit_seed.setText("")
    assert window._validate() is True
    assert window.btn_start.isEnabled() is True


# T-08 / K-02: the scatter buffer is capped regardless of how many points arrive
def test_t08_scatter_buffer_is_capped(window):
    cap = MAX_SCATTER_POINTS
    px = np.random.default_rng(0).random(cap + 5_000)
    py = np.random.default_rng(1).random(cap + 5_000)
    ph = px * px + py * py <= 1.0
    window._on_progress(
        Progress(
            processed=cap + 5_000,
            estimate=3.14,
            error_abs=0.1,
            standard_error=0.05,
            batch_x=px,
            batch_y=py,
            batch_is_hit=ph,
        )
    )
    assert window._px.size == cap
    assert window._py.size == cap
    window.close()
