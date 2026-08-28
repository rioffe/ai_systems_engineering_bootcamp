"""QThread worker that drives the engine off the UI thread (SPEC C-02/C-03).

Guarantees R-09/R-10 and I-007: all sampling happens on the worker thread; the
UI thread only ever receives queued signals. Throttling (C-03) decouples compute
from drawing; a clean active/paused/stopped gate keeps pause/resume/stop simple
and correct (E-04/E-10).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal

from .engine import TRUE_PI, BatchResult, MonteCarloEngine

MAX_EMIT_INTERVAL_SEC = 1.0   # clamp so interval_ms == 0 ("as fast as possible")
# cannot busy-loop the signal queue (E-03).


@dataclass(slots=True)
class Progress:
    processed: int
    estimate: float
    error_abs: float
    standard_error: float
    batch_x: np.ndarray
    batch_y: np.ndarray
    batch_is_hit: np.ndarray


class EstimationWorker(QThread):
    progress = pyqtSignal(object)   # Progress (queued to the UI thread)
    completed = pyqtSignal()
    crashed = pyqtSignal(str)

    def __init__(self, max_emitted_points: int = 60_000) -> None:
        super().__init__()
        self._engine = MonteCarloEngine(None)
        self._max_emitted_points = max_emitted_points
        self._n_total = 0
        self._batch = 1
        self._interval = 0.08   # seconds (80 ms default, C-03)
        self._active = False    # True while running/resumed
        self._stopping = False   # stop() -> thread should exit

    # -- main-thread, thread-safe controls (SPEC C-02) -------------------
    def start_run(
        self, n_total: int, batch: int, interval_ms: int, seed: int | None = None
    ) -> None:
        self._engine = MonteCarloEngine(seed)
        self._n_total = max(0, n_total)
        self._batch = max(1, batch)
        self._interval = max(0.0, min(interval_ms / 1000.0, MAX_EMIT_INTERVAL_SEC))
        self._active = True
        self._stopping = False
        self.start()   # spawns the thread; run() executes below

    def pause(self) -> None:
        self._active = False

    def resume(self) -> None:
        self._active = True
        self._stopping = False

    def stop(self) -> None:
        self._active = False
        self._stopping = True

    # -- worker thread ---------------------------------------------------
    def run(self) -> None:
        try:
            processed = 0
            last_emit = 0.0
            last_emitted = -1    # last processed count actually pushed to the UI
            mono = time.monotonic
            while True:
                # Gate: block until running/resumed; exit on stop.
                if not self._active:
                    if self._stopping:
                        return
                    self.msleep(10)
                    continue

                remaining = self._n_total - processed
                if remaining <= 0:
                    break
                k = min(self._batch, remaining)   # E-02 / I-005 clamp
                batch = self._engine.run_batch(k)
                processed = batch.processed

                # Throttle emission (C-03); interval == 0 => emit every batch.
                now = mono()
                if self._interval <= 0.0 or (now - last_emit) >= self._interval:
                    last_emit = now
                    last_emitted = processed
                    self._emit(batch, processed)

            if self._n_total > 0:
                # Always flush the terminal state so the UI shows the final
                # numbers/points. A fast run can finish inside a single throttle
                # window, so every batch but the first is dropped and the last
                # update is never drawn -- which is exactly the "only the first
                # batch, then COMPLETED/done" symptom. Re-emit the final batch
                # only when it was throttle-dropped, to avoid a double append.
                if last_emitted != processed:
                    self._emit(batch, processed)
                self.completed.emit()
        except Exception as exc:    # E-07: surface, never fabricate a result
            import traceback

            self.crashed.emit(f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")

    def _emit(self, batch: BatchResult, processed: int) -> None:
        est = self._engine.estimate or 0.0
        self.progress.emit(
            Progress(
                processed=processed,
                estimate=est,
                error_abs=abs(est - TRUE_PI),
                standard_error=self._engine.standard_error or 0.0,
                batch_x=batch.x,
                batch_y=batch.y,
                batch_is_hit=batch.is_hit,
            )
        )

    @property
    def engine(self) -> MonteCarloEngine:
        return self._engine
