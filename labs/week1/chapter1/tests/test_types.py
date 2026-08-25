"""T-01 (SPEC section 9.1): Usage arithmetic, invariant I-001.

`Usage.total_tokens` is the sum of `prompt_tokens` and `completion_tokens`, both
of which must be >= 0.
"""

import pytest

from model_playground.types import Usage


@pytest.mark.parametrize(
    "p,c,expected",
    [
        (0, 0, 0),
        (0, 5, 5),
        (3, 0, 3),
        (100, 250, 350),
        (1, 1, 2),
    ],
)
def test_t01_total_tokens_is_sum_of_parts(p, c, expected):
    assert Usage(p, c).total_tokens == expected


@pytest.mark.parametrize("bad", [(-1, 0), (0, -1), (-5, -5)])
def test_t01_negative_counts_raise(bad):
    with pytest.raises(ValueError):
        Usage(*bad)


def test_t01_total_always_geq_each_part():
    for pair in [(0, 0), (1, 1), (7, 42), (1000, 1)]:
        u = Usage(*pair)
        assert u.total_tokens >= u.prompt_tokens
        assert u.total_tokens >= u.completion_tokens
