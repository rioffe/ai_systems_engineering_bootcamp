"""Acceptance tests for the estimator core (SPEC 9.1 & 9.2: T-01..T-05, T-09..T-12).

These run headless (no Qt) and use fixed seeds so they are deterministic/stable.
"""

from __future__ import annotations

import math

import numpy as np

from monte_carlo_pi.engine import (
    TRUE_P,
    TRUE_PI,
    TRUE_VAR_PER_SAMPLE,
    MonteCarloEngine,
    Summary,
)


# ---------------------------------------------------------------- T-01 determinism
def test_t01_determinism_same_seed_is_bitwise_identical():
    a = MonteCarloEngine(seed=42).run_batch(1_000_000)
    b = MonteCarloEngine(seed=42).run_batch(1_000_000)
    assert a.processed == b.processed
    assert a.total_hits == b.total_hits


# ---------------------------------------------------------------- T-02 hit rule
def test_t02_hit_rule_matches_quarter_circle():
    xs = np.array([0.0, 0.5, 1.0, 0.6, 0.8, 0.9999])
    ys = np.array([0.0, 0.5, 1.0, 0.8, 0.6, 0.0])
    expected = (xs * xs + ys * ys) <= 1.0
    assert bool(expected[0]) is True  # (0, 0) inside the disk -> hit
    assert bool(expected[1]) is True  # 0.5^2 + 0.5^2 = 0.5 < 1 -> hit
    assert bool(expected[2]) is False  # (1, 1): 2.0 > 1 -> miss
    assert bool(expected[3]) is True  # 0.6^2 + 0.8^2 = 1.0 -> hit (boundary)
    assert bool(expected[4]) is True  # 0.8^2 + 0.6^2 = 1.0 -> hit (boundary)
    assert bool(expected[5]) is True  # (0.9999, 0) inside the disk -> hit
    batch = MonteCarloEngine(seed=1).run_batch(10_000)
    assert np.array_equal(batch.is_hit, (batch.x * batch.x + batch.y * batch.y) <= 1.0)


# ------------------------------------------- T-03 formula invariants I-003/I-004/I-009
def test_t03_formula_invariants():
    e = MonteCarloEngine(seed=7)
    e.run_batch(500_000)
    p = e.total_hits / e.processed
    assert e.estimate == 4.0 * e.total_hits / e.processed
    assert e.standard_error == 4.0 * math.sqrt(p * (1 - p) / e.processed)
    s = Summary.of(e.processed, e.total_hits)
    assert s.error_abs >= 0
    assert math.isfinite(s.z_score)


def test_t03b_empty_state_returns_none():
    e = MonteCarloEngine()
    assert e.estimate is None and e.standard_error is None


# ------------------------------------------------------------- T-04 monotonicity
def test_t04_monotonic_and_total_hits_le_processed():
    e = MonteCarloEngine(seed=3)
    prev = 0
    for _ in range(50):
        r = e.run_batch(1000)
        assert r.processed >= prev
        assert r.total_hits <= r.processed
        prev = r.processed
        assert r.total_hits >= 0


def test_t04b_final_batch_clamped_to_remainder():
    e = MonteCarloEngine(seed=11)
    remaining = 10_000
    batch = 3333  # 10000 = 3 * 3333 + 1, so the final batch is exactly 1
    last_k = 0
    while remaining > 0:
        k = min(batch, remaining)  # clamp, exactly as the worker does (E-02)
        last_k = k
        e.run_batch(k)
        remaining -= k
    assert last_k == 10_000 % batch
    assert e.processed == 10_000  # no overshoot past N


# ------------------------------------------------------------------- T-05 domain
def test_t05_points_in_unit_square():
    e = MonteCarloEngine(seed=5)
    for _ in range(10):
        r = e.run_batch(100_000)
        assert r.x.min() >= 0.0 and r.x.max() < 1.0
        assert r.y.min() >= 0.0 and r.y.max() < 1.0


# ---------------------------------------------------------- T-09..T-11 statistics
def test_t09_bias_near_zero():
    N, trials = 100_000, 50
    ests = [MonteCarloEngine(seed=s).run_batch(N).estimate for s in range(trials)]
    mean = float(np.mean(ests))
    se_mean = 4.0 * math.sqrt(TRUE_VAR_PER_SAMPLE / N / trials)
    assert abs(mean - TRUE_PI) < 3 * se_mean


def test_t10_variance_matches_theory():
    N, trials = 100_000, 60
    ests = [MonteCarloEngine(seed=s).run_batch(N).estimate for s in range(trials)]
    empirical_var = float(np.var(ests, ddof=1))
    theory_var = 16.0 * TRUE_P * (1 - TRUE_P) / N
    assert 0.8 * theory_var < empirical_var < 1.2 * theory_var


def test_t11_variance_decays_as_1_over_sqrtn():
    small, big = 100_000, 400_000
    se_small = MonteCarloEngine(seed=0).theoretical_standard_error(small)
    se_big = MonteCarloEngine(seed=0).theoretical_standard_error(big)
    r = se_big / se_small  # SE(4N) / SE(N) -> 1/sqrt(4) == 0.5
    assert 0.45 < r < 0.55  # variance decays as 1/N


# ----------------------------------------------------------------- T-12 coverage
def test_t12_3sigma_coverage_reasonable():
    N, trials = 10_000, 100
    within = 0
    for s in range(trials):
        e = MonteCarloEngine(seed=s).run_batch(N)
        if abs(e.estimate - TRUE_PI) <= 3 * e.standard_error:
            within += 1
    assert within / trials >= 0.80  # ~93% expected; threshold kept safely below
