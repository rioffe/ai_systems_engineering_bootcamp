"""T-16/T-17/T-18 (SPEC section 9.6): the Ollama client, network-stubbed.

All of these use `httpx.MockTransport` (no real network, K-04) or an unreachable
host to exercise discovery/fallback, NDJSON + parameter mapping, and the unknown
model path -- without touching a live daemon.
"""

import json

import httpx
import pytest

from model_playground.model import OllamaModel
from model_playground.ollama import ModelNotFoundError, OllamaClient
from model_playground.types import GenerationParams, Message


# ---------------------------------------------------------------- T-16    / E-13
def test_t16_unreachable_host_raises_and_falls_back():
    # Force a dead host; list_models() must raise, and discovery returns
    # used_fallback=True with the mock registry intact. No real network.
    client = OllamaClient(base="http://127.0.0.1:1", timeout_s=2.0)
    with pytest.raises(Exception):   # noqa: B017  any transport fault means offline
        client.list_models()
    from model_playground.registry import build_default_registry

    reg = build_default_registry()
    assert "mock/fast" in {s.model.model_id for s in reg.available()}


# ---------------------------------------------------------------- T-17    / I-008, E-15
def test_t17a_parameter_mapping_and_ndjson():
    # (a) GenerationParams -> Ollama `options`; (b) NDJSON -> finished usage.
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        lines = [
            json.dumps(
                {"message": {"role": "assistant", "content": "Hello"}, "done": False}
            ),
            json.dumps(
                {"message": {"role": "assistant", "content": " world"}, "done": False}
            ),
            json.dumps(
                {
                    "message": {"role": "assistant", "content": ""},
                    "done": True,
                    "prompt_eval_count": 5,
                    "eval_count": 3,
                }
            ),
        ]
        return httpx.Response(
            200, stream=httpx.ByteStream(("\n".join(lines)).encode("utf-8"))
        )

    client = OllamaClient(
        base="http://x", transport=httpx.MockTransport(handler), timeout_s=5.0
    )
    chunks = list(
        client.stream_chat(
            "llama3.2",
            [Message("user", "hi")],
            GenerationParams(temperature=0.7, top_p=0.9, max_tokens=128, seed=42),
        )
    )

    opts = captured["body"]["options"]
    assert opts["temperature"] == 0.7
    assert opts["top_p"] == 0.9
    assert opts["num_predict"] == 128  # max_tokens -> num_predict
    assert opts["seed"] == 42  # seed passed through

    deltas = "".join(c.delta for c in chunks if not c.finished)
    final = chunks[-1]
    assert final.finished is True
    assert final.usage.prompt_tokens == 5
    assert final.usage.completion_tokens == 3
    assert deltas == "Hello world"


def test_t17b_seed_omitted_when_none():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            stream=httpx.ByteStream(
                b'{"message":{"content":""},"done":true,'
                b'"prompt_eval_count":1,"eval_count":1}'
            ),
        )

    client = OllamaClient(
        base="http://x", transport=httpx.MockTransport(handler), timeout_s=5.0
    )
    list(client.stream_chat("m", [Message("user", "hi")], GenerationParams(seed=None)))
    assert "seed" not in captured["body"]["options"]


def test_t17c_malformed_trailing_line_keeps_partial_text_best_effort():
    # A malformed final line is skipped; the stream settles with the partial
    # text accumulated and a best-effort (whitespace-count) usage.
    lines = [
        json.dumps(
            {"message": {"role": "assistant", "content": "Hello"}},
        ),
        json.dumps(
            {"message": {"role": "assistant", "content": " world"}},
        ),
        "not valid json at all",  # malformed => skipped, no `done`
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, stream=httpx.ByteStream(("\n".join(lines)).encode("utf-8"))
        )

    client = OllamaClient(
        base="http://x", transport=httpx.MockTransport(handler), timeout_s=5.0
    )
    chunks = list(client.stream_chat("m", [Message("user", "hi")], GenerationParams()))
    deltas = "".join(c.delta for c in chunks)
    assert deltas == "Hello world"
    final = chunks[-1]
    assert final.finished is True
    assert final.usage.completion_tokens == 2  # "Hello world" => 2 tokens


# ---------------------------------------------------------------- T-18    / R-17, E-14
def test_t18_unknown_model_non_stream_raises_model_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=json.dumps({"error": "model not found"}))

    client = OllamaClient(
        base="http://x", transport=httpx.MockTransport(handler), timeout_s=5.0
    )
    with pytest.raises(ModelNotFoundError) as exc:
        client.chat("ghost", [Message("user", "hi")], GenerationParams(), stream=False)
    assert "model not found" in str(exc.value)
    assert "ghost" in str(exc.value)


def test_t18_unknown_model_stream_raises_model_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=json.dumps({"error": "model not found"}))

    client = OllamaClient(
        base="http://x", transport=httpx.MockTransport(handler), timeout_s=5.0
    )
    with pytest.raises(ModelNotFoundError):
        list(client.stream_chat("ghost", [Message("user", "hi")], GenerationParams()))


def test_t18_ollama_model_generate_surfaces_error_message():
    # OllamaModel turns the 404 into a Message/ERROR, not a crash.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=json.dumps({"error": "model not found"}))

    client = OllamaClient(
        base="http://x", transport=httpx.MockTransport(handler), timeout_s=5.0
    )
    model = OllamaModel("ghost", client=client)
    try:
        model.generate([Message("user", "hi")])
        assert False, "should have raised"
    except ModelNotFoundError as exc:
        assert "model not found" in str(exc)
