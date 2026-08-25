"""T-03..T-06 (SPEC section 9.2): the pure metrics layer.

- T-03: pricing lives in the registry; changing it changes cost_usd (I-003).
- T-04: TTFT ordering + TPS guard (I-004, I-005).
- T-05: cost formula matches N_in*P_in + N_out*P_out exactly (I-006).
- T-06: cost-per-task divides by 1 when no model succeeded (I-007).
"""

import math

from model_playground import metrics as M
from model_playground.model import MockModel
from model_playground.registry import ModelRegistry, ModelSpec
from model_playground.types import Usage


# ---------------------------------------------------------------- T-03  / I-003
def test_t03_pricing_change_flows_through_registry():
    reg = ModelRegistry()
    reg.register(
        ModelSpec(
            MockModel("mock/fast", "fast"),
            price_input_usd_per_1k=0.01,
            price_output_usd_per_1k=0.02,
        )
    )
    usage = Usage(prompt_tokens=1000, completion_tokens=1000)
    c_a = reg.cost_usd("mock/fast", usage)
    assert abs(c_a - (0.01 + 0.02)) < 1e-12
    # Mutate the registry price (the ONLY place prices live, I-003).
    spec = reg.get("mock/fast")
    spec.price_output_usd_per_1k = 0.50
    c_b = reg.cost_usd("mock/fast", usage)
    assert c_b != c_a
    assert abs(c_b - (0.01 + 1000 / 1000.0 * 0.50)) < 1e-12


def test_t03_default_local_price_is_zero():
    reg = ModelRegistry()
    reg.register(ModelSpec(MockModel("mock/fast", "fast")))
    assert reg.cost_usd("mock/fast", Usage(1000, 1000)) == 0.0


# ---------------------------------------------------------------- T-04  / I-004, I-005
def test_t04_ttft_never_exceeds_total():
    m = M.compute_metrics(
        "m",
        t_request=0.0,
        t_first_token=0.1,
        t_complete=0.5,
        usage=Usage(10, 40),
        price_input=0.0,
        price_output=0.0,
    )
    assert m.ttft_ms <= m.total_latency_ms


def test_t04_non_streaming_ttft_equals_total():
    # E-04 / I-004: no first-token clock => TTFT is defined as the total latency.
    m = M.compute_metrics(
        "m",
        t_request=0.0,
        t_first_token=None,
        t_complete=0.3,
        usage=Usage(10, 40),
        price_input=0.0,
        price_output=0.0,
    )
    assert abs(m.ttft_ms - m.total_latency_ms) < 1e-9


def test_t04_zero_generation_duration_gives_zero_tps():
    # E-04: TTFT == total => generation interval is zero => tps must be 0.0.
    m = M.compute_metrics(
        "m",
        t_request=0.0,
        t_first_token=None,
        t_complete=0.3,
        usage=Usage(10, 40),
        price_input=0.0,
        price_output=0.0,
    )
    assert m.tps == 0.0
    assert math.isfinite(m.tps)


def test_t04_zero_completion_tokens_gives_zero_tps():
    # E-05: an empty completion still yields tps == 0.0, never inf/nan.
    m = M.compute_metrics(
        "m",
        t_request=0.0,
        t_first_token=0.0,
        t_complete=0.2,
        usage=Usage(5, 0),
        price_input=0.0,
        price_output=0.0,
    )
    assert m.tps == 0.0
    assert math.isfinite(m.tps)


def test_t04_ttft_capped_when_first_token_late_by_float_error():
    # A first_token clock slightly past complete must not make TTFT > total.
    m = M.compute_metrics(
        "m",
        t_request=0.0,
        t_first_token=1.0,
        t_complete=0.9,
        usage=Usage(1, 3),
        price_input=0.0,
        price_output=0.0,
    )
    assert m.ttft_ms <= m.total_latency_ms


# ---------------------------------------------------------------- T-05  / I-006
def test_t05_cost_formula_exact():
    usage = Usage(prompt_tokens=1234, completion_tokens=5678)
    p_in, p_out = 0.0123, 0.0456
    m = M.compute_metrics(
        "m",
        t_request=0.0,
        t_first_token=None,
        t_complete=1.0,
        usage=usage,
        price_input=p_in,
        price_output=p_out,
    )
    expected = 1234 / 1000.0 * p_in + 5678 / 1000.0 * p_out
    assert m.cost_usd == expected
    assert M.cost_usd(usage, p_in, p_out) == expected


# ---------------------------------------------------------------- T-06  / I-007
def test_t06_all_failed_run_uses_denominator_1():
    assert M.cost_per_success_task(0.42, 0) == 0.42
    # No division by zero, even with zero cost.
    assert M.cost_per_success_task(0.0, 0) == 0.0


def test_t06_mixed_run_divides_by_success_count():
    total = 0.30
    assert abs(M.cost_per_success_task(total, 3) - 0.10) < 1e-12
    assert abs(M.cost_per_success_task(total, 1) - 0.30) < 1e-12
