"""Pure Monte Carlo pi estimation core (SPEC C-01).

No Qt or matplotlib imports: fully testable headless, source of truth for I-002..I-004.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

TRUE_PI = math.pi
TRUE_P = TRUE_PI / 4.0
TRUE_VAR_PER_SAMPLE = TRUE_P * (1.0 - TRUE_P)


@dataclass(slots=True)
class BatchResult:
    processed: int
    total_hits: int
    hits_this_batch: int
    x: np.ndarray
    y: np.ndarray
    is_hit: np.ndarray

    @property
    def estimate(self) -> float:
        return 4.0 * self.total_hits / self.processed

    @property
    def standard_error(self) -> float:
        p = self.total_hits / self.processed
        return 4.0 * math.sqrt(p * (1.0 - p) / self.processed)


@dataclass(slots=True)
class Summary:
    n_total: int
    estimate: float
    error_abs: float
    standard_error: float
    z_score: float

    @staticmethod
    def of(processed: int, total_hits: int) -> Summary:
        estimate = 4.0 * total_hits / processed
        p = total_hits / processed
        se = 4.0 * math.sqrt(p * (1.0 - p) / processed)
        err = abs(estimate - TRUE_PI)
        z = err / se if se > 0 else float("inf")
        return Summary(processed, estimate, err, se, z)


class MonteCarloEngine:
    def __init__(self, seed: int | None = None) -> None:
        self._rng = np.random.default_rng(seed)
        self._processed = 0
        self._total_hits = 0

    def run_batch(self, n: int) -> BatchResult:
        if n < 0:
            raise ValueError("n must be >= 0")
        x = self._rng.random(n)
        y = self._rng.random(n)
        is_hit = (x * x + y * y) <= 1.0
        hits = int(is_hit.sum())
        self._processed += n
        self._total_hits += hits
        return BatchResult(self._processed, self._total_hits, hits, x, y, is_hit)

    @property
    def processed(self) -> int:
        return self._processed

    @property
    def total_hits(self) -> int:
        return self._total_hits

    @property
    def estimate(self) -> float | None:
        return 4.0 * self._total_hits / self._processed if self._processed > 0 else None

    @property
    def standard_error(self) -> float | None:
        p = self._total_hits / self._processed if self._processed > 0 else 0.0
        return (
            4.0 * math.sqrt(p * (1.0 - p) / self._processed)
            if self._processed > 0
            else None
        )

    def theoretical_standard_error(self, n: int) -> float:
        if n <= 0:
            raise ValueError("n must be > 0")
        return 4.0 * math.sqrt(TRUE_VAR_PER_SAMPLE / n)
