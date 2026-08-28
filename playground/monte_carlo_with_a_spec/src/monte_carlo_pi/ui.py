"""MainWindow: PyQt5 + matplotlib UI (SPEC section 5 / C-05 / C-06 / K-01/K-05).

The UI performs no sampling of its own (R-10, I-008): it only configures the
worker and reacts to the worker's queued signal updates on the UI thread.
"""

from __future__ import annotations

import math

import numpy as np
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt5.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .engine import TRUE_PI
from .worker import EstimationWorker, Progress

# Lets the offscreen test suite (tests/test_ui.py) skip gracefully if Qt is
# unavailable somewhere (SPEC E-11). True whenever this module imported.
MAIN_WINDOW_AVAILABLE = True
MAX_SCATTER_POINTS = 60_000  # K-02: plotting memory is bounded regardless of N
MAX_HISTORY_POINTS = 5_000  # convergence-line resolution cap


class MainWindow(QMainWindow):
    def __init__(self, app: QApplication | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Monte Carlo pi Estimator")
        self._worker: EstimationWorker | None = None

        root = QVBoxLayout()
        root.addLayout(self._build_controls())
        root.addLayout(self._build_stats())
        splitter = QSplitter()
        self.scatter_container, self.scatter, self.scatter_fig = self._make_canvas(
            0, "x", "y"
        )
        self.conv_container, self.convergence, self.conv_fig = self._make_canvas(
            0, "samples (log)", "pi_hat"
        )
        splitter.addWidget(self.scatter_container)
        splitter.addWidget(self.conv_container)
        root.addWidget(splitter, 1)
        self.setCentralWidget(QWidget())
        self.centralWidget().setLayout(root)

        self._px = np.empty(0, dtype=np.float64)
        self._py = np.empty(0, dtype=np.float64)
        self._hist_n: list[float] = []
        self._hist_est: list[float] = []

        self._connect()
        self._validate()

    # --------------------------------------------------------------- controls
    def _make_canvas(self, subplot: int, xlabel: str, ylabel: str):
        """Return (container QWidget, FigureCanvas) for embedding in a layout."""
        fig = Figure()
        ax = fig.add_subplot(1, 1, 1)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        canvas = FigureCanvas(fig)
        container = QWidget()
        cbox = QVBoxLayout(container)
        cbox.setContentsMargins(0, 0, 0, 0)
        cbox.addWidget(canvas)
        container.setFixedHeight(360)
        return container, canvas, fig

    def _build_controls(self) -> QGridLayout:
        g = QGridLayout()
        self.spin_n = QSpinBox()
        self.spin_n.setRange(1, 1_000_000_000)
        self.spin_n.setValue(1_000_000)
        self.spin_batch = QSpinBox()
        self.spin_batch.setRange(1, 10_000_000)
        self.spin_batch.setValue(100_000)
        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(0, 1000)
        self.spin_interval.setValue(80)
        self.edit_seed = QLineEdit()
        self.edit_seed.setPlaceholderText("<blank = random>")

        self.btn_start = QPushButton("Start")
        self.btn_pause = QPushButton("Pause")
        self.btn_resume = QPushButton("Resume")
        self.btn_reset = QPushButton("Reset")

        fields = [
            ("Total samples N", self.spin_n),
            ("Batch size B", self.spin_batch),
            ("Update interval (ms)", self.spin_interval),
            ("RNG seed", self.edit_seed),
        ]
        for i, (label, w) in enumerate(fields):
            g.addWidget(QLabel(label), i, 0)
            g.addWidget(w, i, 1)

        row = QHBoxLayout()
        for b in (self.btn_start, self.btn_pause, self.btn_resume, self.btn_reset):
            row.addWidget(b)
        row.addStretch(1)
        g.addLayout(row, 4, 0, 1, 2)
        return g

    def _build_stats(self) -> QHBoxLayout:
        h = QHBoxLayout()
        self.lbl_estimate = QLabel("pi_hat: --")
        self.lbl_error = QLabel("|error|: --")
        self.lbl_se = QLabel("std err: --")
        self.lbl_z = QLabel("z-score: --")
        self.lbl_progress = QLabel("processed: 0 / 0")
        self.lbl_state = QLabel("state: IDLE")
        self.lbl_msg = QLabel("")
        for w in (
            self.lbl_estimate,
            self.lbl_error,
            self.lbl_se,
            self.lbl_z,
            self.lbl_progress,
            self.lbl_state,
            self.lbl_msg,
        ):
            h.addWidget(w)
        h.addStretch(1)
        return h

    # --------------------------------------------------------------- plots
    def _init_scatter_axes(self) -> None:
        ax = self.scatter_fig.axes[0]
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_aspect("equal")
        theta = np.linspace(0, math.pi / 2, 200)
        ax.plot(np.cos(theta), np.sin(theta), color="k", linewidth=1)
        self._hit_scatter = ax.scatter([], [], s=2, c="#2e7d32", label="hit")
        self._miss_scatter = ax.scatter([], [], s=2, c="#c62828", label="miss")
        ax.legend(loc="upper right")

    def _init_convergence_axes(self) -> None:
        ax = self.conv_fig.axes[0]
        ax.set_xscale("log")
        ax.axhline(TRUE_PI, color="red", linestyle="--", label="true pi")
        (self._hist_line,) = ax.plot([], [], linewidth=0.7, label="pi_hat(n)")
        (self._band3,) = ax.plot(
            [], [], color=(0.1, 0.5, 0.1), alpha=0.4, label="+/-3 sigma"
        )
        (self._band2,) = ax.plot(
            [], [], color=(0.1, 0.8, 0.1), alpha=0.5, label="+/-2 sigma"
        )
        ax.legend(loc="lower right")

    # --------------------------------------------------------------- wiring
    def _connect(self) -> None:
        for box in (self.spin_n, self.spin_batch, self.spin_interval):
            box.valueChanged.connect(self._validate)
        self.edit_seed.textChanged.connect(self._validate)
        self.btn_start.clicked.connect(self.on_start)
        self.btn_pause.clicked.connect(self._pause_handler)
        self.btn_resume.clicked.connect(self._resume_handler)
        self.btn_reset.clicked.connect(self.on_reset)
        self._init_scatter_axes()
        self._init_convergence_axes()

    def _connect_worker_signals(self, worker: EstimationWorker) -> None:
        worker.progress.connect(self._on_progress)
        worker.completed.connect(self._on_completed)
        worker.crashed.connect(self._on_crashed)

    # --------------------------------------------------------------- validity
    def _seed_value(self) -> int | None:
        txt = self.edit_seed.text().strip()
        if txt == "":
            return None
        try:
            return int(txt)
        except ValueError:
            return None

    def _validate(self, *_args) -> bool:
        ok = True
        msg = ""
        if self.spin_n.value() < 1:
            ok = False
            msg = "N must be >= 1"
        seed_txt = self.edit_seed.text().strip()
        if seed_txt != "" and self._seed_value() is None:
            ok = False
            msg = "Seed must be an integer or blank"
        self.lbl_msg.setText(msg)
        self.btn_start.setEnabled(ok)
        return ok

    # --------------------------------------------------------------- actions
    def on_start(self) -> None:
        if not self._validate():
            return
        self._stop_worker()  # I-007: exactly one live worker
        seed = self._seed_value()
        self._px = np.empty(0, dtype=np.float64)
        self._py = np.empty(0, dtype=np.float64)
        self._hist_n.clear()
        self._hist_est.clear()
        self._refresh_scatter()
        self._refresh_convergence()
        self._worker = EstimationWorker(max_emitted_points=MAX_SCATTER_POINTS)
        self._connect_worker_signals(self._worker)
        self._worker.start_run(
            self.spin_n.value(),
            self.spin_batch.value(),
            self.spin_interval.value(),
            seed,
        )
        self._set_running(True)
        self.lbl_state.setText("state: RUNNING")

    def _pause_handler(self) -> None:
        if self._worker is not None:
            self._worker.pause()
            self.lbl_state.setText("state: PAUSED")

    def _resume_handler(self) -> None:
        if self._worker is not None:
            self._worker.resume()
            self.lbl_state.setText("state: RUNNING")

    def on_reset(self) -> None:
        self._stop_worker()
        self._px = np.empty(0, dtype=np.float64)
        self._py = np.empty(0, dtype=np.float64)
        self._hist_n.clear()
        self._hist_est.clear()
        self._refresh_scatter()
        self._refresh_convergence()
        self._set_running(False)
        self.lbl_state.setText("state: IDLE")
        self.lbl_msg.setText("")

    def _stop_worker(self) -> None:
        w = self._worker
        self._worker = None
        if w is not None:
            w.stop()
            w.wait()

    # --------------------------------------------------------------- handlers
    def _on_progress(self, p: Progress) -> None:
        self._px = np.concatenate([self._px, p.batch_x])
        self._py = np.concatenate([self._py, p.batch_y])
        if self._px.size > MAX_SCATTER_POINTS:  # K-02: keep the recent tail
            self._px = self._px[-MAX_SCATTER_POINTS:]
            self._py = self._py[-MAX_SCATTER_POINTS:]
        self._hist_n.append(p.processed)
        self._hist_est.append(p.estimate)
        self._update_stats(p.processed, p.estimate, p.error_abs, p.standard_error)
        self._refresh_scatter()
        self._refresh_convergence()

    def _on_completed(self) -> None:
        self._set_running(False)
        self.lbl_state.setText("state: COMPLETED")
        self.lbl_msg.setText("done")

    def _on_crashed(self, message: str) -> None:  # E-07: never fabricate
        self._set_running(False)
        self.lbl_state.setText("state: ERROR")
        QMessageBox.critical(self, "Estimation error", message)

    # --------------------------------------------------------------- drawing
    def _refresh_scatter(self) -> None:
        r2 = self._px * self._px + self._py * self._py
        hit = r2 <= 1.0
        self._hit_scatter.set_offsets(np.column_stack([self._px[hit], self._py[hit]]))
        self._miss_scatter.set_offsets(
            np.column_stack([self._px[~hit], self._py[~hit]])
        )
        self.scatter.draw()

    def _refresh_convergence(self) -> None:
        n_tail = self._hist_n[-MAX_HISTORY_POINTS:]
        est_tail = self._hist_est[-MAX_HISTORY_POINTS:]
        self._hist_line.set_data(n_tail, est_tail)
        n = max(self._hist_n) if self._hist_n else 0
        if n > 0:
            log10n = math.log10(n)
            xs = np.logspace(0, max(log10n, 1.0), 200)
            var_per_sample = (TRUE_PI / 4.0) * (1.0 - TRUE_PI / 4.0)
            se_of = 4.0 * math.sqrt(var_per_sample) * np.power(10.0, -0.5 * xs)
            for band, k in ((self._band3, 3), (self._band2, 2)):
                band.set_xdata(xs)
                band.set_ydata(TRUE_PI + k * se_of)
        self.convergence.draw()

    # --------------------------------------------------------------- helpers
    def _set_running(self, running: bool) -> None:
        self.btn_pause.setEnabled(running)
        self.btn_resume.setEnabled(running)
        self.btn_start.setEnabled(not running and self._validate())

    def _update_stats(self, processed: int, est: float, err: float, se: float) -> None:
        self.lbl_estimate.setText(f"pi_hat: {est:.6f}")
        self.lbl_error.setText(f"|error|: {err:.6f}")
        self.lbl_se.setText(f"std err: {se:.6f}")
        z = err / se if se > 0 else float("inf")
        self.lbl_z.setText(f"z-score: {z:.3f}")
        self.lbl_progress.setText(f"processed: {processed:,} / {self.spin_n.value():,}")

    def closeEvent(self, event) -> None:  # E-10
        self._stop_worker()
        super().closeEvent(event)
