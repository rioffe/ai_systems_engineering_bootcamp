#!/usr/bin/env python3
"""Monte Carlo Pi estimation with a PyQt5 + matplotlib GUI.

The idea of the Monte Carlo method:
    Inscribed in the unit square [0, 1] x [0, 1] is a quarter circle of radius 1.
    The quarter circle has area pi/4 and the square has area 1, so the chance that
    a uniformly random point in the square falls inside the quarter circle (x^2 +
    y^2 <= 1) equals pi/4. Sampling N points and counting the hits gives
    pi ~= 4 * hits / N, and the estimate converges to true pi as N grows.
"""
from __future__ import annotations

import math
import sys

import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import matplotlib

matplotlib.use("Qt5Agg")
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


# How many random points each animation frame adds.
BATCH_SIZE = 5_000
# Max points actually drawn on the scatter (keeps drawing snappy). The running
# estimate still uses the full, unbounded sample count.
MAX_SCATTER_POINTS = 500_000


class PiEstimatorThread(QThread):
    """Samples random points on a background thread.

    Emits ``batch_ready`` with (x, y) arrays for each batch so the main window
    can render it and update the running Pi estimate without freezing the UI.
    """

    batch_ready = pyqtSignal(object, object)   # x-array, y-array
    finished_message = pyqtSignal(str)

    def __init__(self, target_total: int, batch_size: int,
                 rng: np.random.Generator, start_offset: int):
        super().__init__()
        self.target_total = target_total
        self.batch_size = batch_size
        self.rng = rng
        self.start_offset = start_offset
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        produced = self.start_offset
        while produced < self.target_total and not self._stop:
            n = min(self.batch_size, self.target_total - produced)
            batch = self.rng.random((n, 2))
            produced += n
            self.batch_ready.emit(batch[:, 0], batch[:, 1])
        self.finished_message.emit(
            f"Done. Sampled {produced} points."
            if not self._stop else "Stopped early.")


class MonteCarloPiWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Monte Carlo Pi")
        self.resize(1000, 700)

        # Unbounded running statistics.
        self._total_points = 0
        self._inside_count = 0
        self._convergence_x: list[int] = []
        self._convergence_y: list[float] = []

        # Bounded buffers of points to actually draw.
        self._in_inside: list[np.ndarray] = []
        self._in_inside_y: list[np.ndarray] = []
        self._in_outside: list[np.ndarray] = []
        self._in_outside_y: list[np.ndarray] = []

        self._thread: PiEstimatorThread | None = None

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.addWidget(self._build_controls())
        layout.addWidget(self._build_figure())
        layout.addWidget(self._build_stats())

    # -- UI construction ---------------------------------------------------

    def _build_controls(self) -> QWidget:
        add_btn = QPushButton("Add 1M points")
        add_btn.clicked.connect(lambda: self._start_sampler(1_000_000))
        add_more_btn = QPushButton("Add 10M (to total)")
        add_more_btn.clicked.connect(lambda: self._start_sampler(10_000_000))
        stop_btn = QPushButton("Stop")
        stop_btn.clicked.connect(self._stop_sampler)
        reset_btn = QPushButton("Reset")
        reset_btn.clicked.connect(self._reset)

        row = QWidget()
        row_layout = QHBoxLayout(row)
        for b in (add_btn, add_more_btn, stop_btn, reset_btn):
            row_layout.addWidget(b)
        row_layout.addStretch(1)
        return row

    def _build_figure(self) -> QWidget:
        self.fig = Figure()
        self.scatter_ax = self.fig.add_subplot(1, 2, 1)   # live scatter
        self.convergence_ax = self.fig.add_subplot(1, 2, 2)  # convergence
        self._setup_scatter_ax()
        self._setup_convergence_ax()
        self.canvas = FigureCanvas(self.fig)
        return self.canvas

    def _setup_scatter_ax(self) -> None:
        ax = self.scatter_ax
        ax.set_title("Unit square with quarter circle")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_aspect("equal")
        ax.grid(True, alpha=0.3)
        theta = np.linspace(0, math.pi / 2, 100)
        ax.plot(np.cos(theta), np.sin(theta), color="black", linewidth=1.5)
        self.scatter_inside = ax.scatter([], [], s=1.0, color="green", alpha=0.4)
        self.scatter_outside = ax.scatter([], [], s=1.0, color="red", alpha=0.15)

    def _setup_convergence_ax(self) -> None:
        ax = self.convergence_ax
        ax.set_title("Pi estimate vs samples")
        ax.set_xlabel("Number of samples")
        ax.set_ylabel("Pi estimate")
        ax.axhline(math.pi, color="black", linestyle="--",
                   linewidth=1, label="true pi")
        ax.grid(True, alpha=0.3)
        self.convergence_line, = ax.plot([], [], color="blue", linewidth=1)
        ax.legend(loc="best")

    def _build_stats(self) -> QWidget:
        self.stats_label = QLabel()
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.addWidget(self.stats_label)
        layout.addStretch(1)
        self._update_stats_label()
        return w

    # -- sampling / logic --------------------------------------------------

    def _start_sampler(self, total: int) -> None:
        if self._thread is not None and self._thread.isRunning():
            self._thread.stop()
            self._thread.wait()
        rng = np.random.default_rng()
        self._thread = PiEstimatorThread(
            target_total=total,
            batch_size=BATCH_SIZE,
            rng=rng,
            start_offset=self._total_points,
        )
        self._thread.batch_ready.connect(self._on_batch)
        self._thread.finished_message.connect(lambda m: self._update_stats_label())
        self._thread.start()

    def _stop_sampler(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            self._thread.stop()
            self._thread.wait()

    def _on_batch(self, x: np.ndarray, y: np.ndarray) -> None:
        inside = x * x + y * y <= 1.0
        self._total_points += x.size
        self._inside_count += int(inside.sum())

        # Append point batches and trim the draw buffers to MAX_SCATTER_POINTS.
        self._in_inside.append(x[inside])
        self._in_inside_y.append(y[inside])
        self._in_outside.append(x[~inside])
        self._in_outside_y.append(y[~inside])
        self._redraw_scatter()

        self._convergence_x.append(self._total_points)
        self._convergence_y.append(self._current_pi_estimate())
        self.convergence_line.set_data(self._convergence_x, self._convergence_y)

        self._update_stats_label()
        self.canvas.draw_idle()

    def _current_pi_estimate(self) -> float:
        if self._total_points == 0:
            return float("nan")
        return 4.0 * self._inside_count / self._total_points

    def _capped_offsets(self, xs: list[np.ndarray],
                        ys: list[np.ndarray]) -> np.ndarray:
        x_arr = np.concatenate(xs) if xs else np.array([], dtype=float)
        y_arr = np.concatenate(ys) if ys else np.array([], dtype=float)
        if x_arr.size > MAX_SCATTER_POINTS:
            x_arr = x_arr[-MAX_SCATTER_POINTS:]
            y_arr = y_arr[-MAX_SCATTER_POINTS:]
        return np.column_stack((x_arr, y_arr))

    def _redraw_scatter(self) -> None:
        self.scatter_inside.set_offsets(
            self._capped_offsets(self._in_inside, self._in_inside_y))
        self.scatter_outside.set_offsets(
            self._capped_offsets(self._in_outside, self._in_outside_y))

    def _update_stats_label(self) -> None:
        est = self._current_pi_estimate()
        if math.isnan(est):
            est_str = "n/a"
        else:
            est_str = f"{est:.10f}   (error {abs(est - math.pi):.3e})"
        self.stats_label.setText(
            f"Samples: {self._total_points:,}     "
            f"Inside: {self._inside_count:,}     "
            f"Pi estimate: {est_str}")

    def _reset(self) -> None:
        self._stop_sampler()
        self._total_points = 0
        self._inside_count = 0
        self._convergence_x = []
        self._convergence_y = []
        for lst in (self._in_inside, self._in_inside_y,
                    self._in_outside, self._in_outside_y):
            lst.clear()
        self.scatter_inside.set_offsets(np.empty((0, 2)))
        self.scatter_outside.set_offsets(np.empty((0, 2)))
        self.convergence_line.set_data([], [])
        self._update_stats_label()
        self.canvas.draw_idle()


def main() -> None:
    argv = [sys.argv[0]] + sys.argv[1:]
    app = QApplication(argv)
    win = MonteCarloPiWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
