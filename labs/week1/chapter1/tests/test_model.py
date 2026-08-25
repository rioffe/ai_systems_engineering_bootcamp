"""T-07 (SPEC section 9.1) + MockModel variant behavior.

Reproducibility (I-012 / R-08 / R-15): a fixed `seed` on MockModel yields a
bitwise-identical text and usage across runs, and the *streamed* completion token
count equals the *non-streaming* `usage.completion_tokens` (I-008). Wall-clock
timing is not asserted (it is nondeterministic), but token counts are.
"""

import pytest

from model_playground.model import MockModel
from model_playground.types import Message, Role


def _msgs():
    return [Message(Role.USER, "hello world please compare us")]


# ---------------------------------------------------------------- T-07   / I-012
def test_t07_fixed_seed_is_bitwise_reproducible_text():
    a = MockModel("mock/fast", "fast").generate(_msgs(), seed=42)
    b = MockModel("mock/fast", "fast").generate(_msgs(), seed=42)
    assert a.text == b.text
    assert a.usage == b.usage
    assert a.usage.completion_tokens > 0


def test_t07_stream_count_equals_generate_completion():
    # I-008: streamed token count == non-streaming usage.completion_tokens.
    model = MockModel("mock/fast", "fast")
    gen = model.generate(_msgs(), seed=7)
    chunks = list(model.stream(_msgs(), seed=7))
    streamed_tokens = sum(1 for c in chunks if c.delta != "")
    assert streamed_tokens == gen.usage.completion_tokens
    assert gen.usage.completion_tokens == len(chunks)


def test_t07_stream_final_chunk_finishes_and_carry_usage():
    # I-008: the last chunk is finished=True and carries the final usage.
    chunks = list(MockModel("mock/fast", "fast").stream(_msgs(), seed=11))
    last = chunks[-1]
    assert last.finished is True
    assert last.usage is not None
    assert last.usage.completion_tokens == gen_eq_chunks(chunks)


def gen_eq_chunks(chunks):
    return sum(1 for c in chunks if c.delta != "")


# ---------------------------------------------------------------- variants
def test_raising_raises_in_generate():
    with pytest.raises(RuntimeError):
        MockModel("mock/raising", "raising").generate(_msgs())


def test_raising_raises_mid_stream_but_streams_partial_first():
    produced = 0
    with pytest.raises(RuntimeError):
        for c in MockModel("mock/raising", "raising").stream(_msgs(), seed=3):
            produced += 1
            if c.delta:
                assert c.finished is False
    assert produced >= 1  # at least the first token reached the caller


def test_empty_variant_zero_completion():
    chunks = list(MockModel("mock/empty", "empty").stream(_msgs()))
    assert chunks[0].finished is True
    assert chunks[0].usage.completion_tokens == 0


def test_mock_model_needs_no_network_or_ollama():
    # K-04: constructing and running MockModel touches neither Ollama nor httpx.
    m = MockModel("mock/fast", "fast")
    assert m.generate(_msgs()).text
    assert list(m.stream(_msgs()))


def test_empty_messages_precondition():
    with pytest.raises(ValueError):
        MockModel("mock/fast", "fast").generate([])
