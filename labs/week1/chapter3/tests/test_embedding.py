"""Tests for rag.embedding -- MockEmbedder FNV-1a + OllamaEmbedder interface.

Implements T-03 / T-04 / T-23 (SPEC C-02 / R-02).
"""

from __future__ import annotations

from rag.embedding import (
    MockEmbedder,
    OllamaEmbedder,
    fnv1a32,
    tokenizer,
)

FNV_OFFSET = 0x811C9DC5
FNV_PRIME = 0x01000193
FNV_MASK = 0xFFFFFFFF


def test_fnv1a32_known_value():
    # FNV-1a 32-bit of "a": h = offset; h = (h XOR 0x61) * prime, masked.
    h = fnv1a32("a")
    expected = ((FNV_OFFSET ^ 0x61) * FNV_PRIME) & FNV_MASK
    assert h == expected
    # Process-independent: identical input gives identical output.
    assert fnv1a32("hello") == fnv1a32("hello")
    # Differ from Python's per-process built-in hash.
    assert h != hash("a")


def test_tokenizer_matches_spec():
    # O-1a: lowercase, split on [^\w']+, drop empty; apostrophe is kept
    # (it is inside the negated set), so words are not split inside.
    assert tokenizer("Hello, World! Foo'bar") == ["hello", "world", "foo'bar"]
    assert tokenizer("") == []
    assert tokenizer("a b c") == ["a", "b", "c"]
    # Digits and underscores survive \w; a space still splits tokens.
    assert tokenizer("v1.2_3 x") == ["v1", "2_3", "x"]


def test_mock_embedder_l2_normalized():
    emb = MockEmbedder()
    vec = emb.embed("hello world")
    norm = sum(x * x for x in vec) ** 0.5
    assert abs(norm - 1.0) < 1e-9


def test_mock_embedder_is_deterministic():
    emb = MockEmbedder()
    v1 = emb.embed("test document")
    v2 = emb.embed("test document")
    assert v1 == v2


def test_mock_embedder_shared_vocab_has_nonzero_cosine():
    emb = MockEmbedder()
    v1 = emb.embed("hello world")
    v2 = emb.embed("hello world")
    cosine = sum(a * b for a, b in zip(v1, v2))
    assert cosine > 0.99


def test_mock_embedder_dim_default():
    emb = MockEmbedder()
    assert emb.dim == 256


def test_mock_embedder_custom_dim():
    emb = MockEmbedder(dim=128)
    vec = emb.embed("hello world")
    assert len(vec) == 128


def test_mock_embedder_model_id():
    emb = MockEmbedder()
    assert emb.model_id == "mock"


def test_mock_embedder_different_tokens_give_different_vectors():
    emb = MockEmbedder()
    v1 = emb.embed("alpha beta gamma")
    v2 = emb.embed("delta epsilon zeta")
    assert v1 != v2


def test_ollama_embedder_interface():
    assert hasattr(OllamaEmbedder, "embed")
    assert hasattr(OllamaEmbedder, "dim")
    assert hasattr(OllamaEmbedder, "model_id")


# ---------------------------------------------------------------------------
# OllamaEmbedder live contract (offline via a monkeypatched httpx.post).
# The batch endpoint /api/embed takes "input"; the LEGACY /api/embeddings
# endpoint took "prompt". Posting "prompt" to /api/embed is silently accepted
# and returns {"embeddings": []} with HTTP 200 -- so the field name is
# load-bearing and the error paths must say what actually happened.
# ---------------------------------------------------------------------------


def _fake_ollama(monkeypatch, payload):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json

        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return payload

        return _Resp()

    monkeypatch.setattr("httpx.post", fake_post)
    return captured


def test_ollama_embedder_posts_input_not_prompt(monkeypatch):
    captured = _fake_ollama(monkeypatch, {"embeddings": [[0.5, -0.25, 0.0, 1.0]]})
    vec = OllamaEmbedder(model="nomic-embed-text:latest").embed("hello")
    assert captured["json"] == {"model": "nomic-embed-text:latest", "input": "hello"}
    assert "prompt" not in captured["json"]
    assert vec == (0.5, -0.25, 0.0, 1.0)


def test_ollama_embedder_default_model_is_the_pulled_tag(monkeypatch):
    # availability._probe exact-matches --embed-model against /api/tags names,
    # and Ollama serves this model only as "nomic-embed-text:latest"; the
    # untagged default would always be PULL_REQUIRED.
    assert OllamaEmbedder().model == "nomic-embed-text:latest"


def test_ollama_embedder_legacy_single_embedding_shape(monkeypatch):
    # The legacy /api/embeddings shape {"embedding": [...]} is still accepted.
    _fake_ollama(monkeypatch, {"embedding": [0.1, 0.2]})
    assert OllamaEmbedder().embed("x") == (0.1, 0.2)


def test_ollama_embedder_empty_embeddings_is_a_useful_error(monkeypatch):
    # A "prompt" body against /api/embed yields {"embeddings": []} (HTTP 200);
    # the error must name the empty result and the field the endpoint wants.
    _fake_ollama(monkeypatch, {"embeddings": []})
    try:
        OllamaEmbedder().embed("x")
        assert False, "expected ValueError"
    except ValueError as exc:
        msg = str(exc)
        assert "empty" in msg
        assert "embeddings" in msg
        assert "input" in msg
        assert "unexpected /api/embed response shape" not in msg


def test_ollama_embedder_top_level_error_surfaced(monkeypatch):
    _fake_ollama(monkeypatch, {"error": "model 'nope' not found"})
    try:
        OllamaEmbedder().embed("x")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "model 'nope' not found" in str(exc)
