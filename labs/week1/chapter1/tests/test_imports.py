"""T-02 (SPEC section 9.1): interface purity / K-04.

The only provider-aware module is ollama.py (where the single `import httpx`
lives). No module names a vendor SDK. And the app discovers and runs a MockModel
with no Ollama and no keys.
"""

import re

from model_playground.registry import build_default_registry, discover_registry
from model_playground.types import Message

SRC = "src/model_playground"


def _module_sources():
    import glob
    import os

    paths = sorted(glob.glob(f"{SRC}/*.py"))
    assert paths, "no source modules found under " + SRC
    return {os.path.basename(p): open(p, encoding="utf-8").read() for p in paths}


def test_t02_httpx_imports_only_in_ollama():
    sources = _module_sources()
    offenders = [
        name
        for name, text in sources.items()
        if re.search(r"\b(import|from)\b.*\bhttpx\b", text)
    ]
    assert offenders == ["ollama.py"], offenders


def test_t02_no_vendor_sdk_named_anywhere():
    sources = _module_sources()
    vendors = ["openai", "anthropic", "cohere", "azure.ai", "google.generativeai"]
    # Match each vendor as a standalone identifier, not a bare substring: a bare
    # `v in text` spuriously flags coincidental substrings (e.g. the word
    # "coherent" contains "cohere") while still catching a real reference.
    for text in sources.values():
        for v in vendors:
            pat = r"(?<![A-Za-z0-9_])" + re.escape(v) + r"(?![A-Za-z0-9_])"
            m = re.search(pat, text)
            assert m is None, f"vendor SDK named: {v}"


def test_t02_provider_shape_leaks_only_in_ollama():
    # No concrete endpoint/shape leaks outside OllamaClient (I-002).
    sources = {n: t for n, t in _module_sources().items() if n != "ollama.py"}
    for name, text in sources.items():
        assert "localhost:11434" not in text, name
        assert "/api/chat" not in text, name
        assert "/api/tags" not in text, name


def test_t02_offline_no_ollama_no_keys(monkeypatch):
    # K-04: discover + run a MockModel with Ollama unreachable and no key.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    reg, used_fallback = discover_registry(ollama_host="http://127.0.0.1:1")
    assert used_fallback is True
    assert "mock/fast" in {s.model.model_id for s in reg.available()}
    spec = reg.get("mock/fast")
    out = spec.model.generate([Message("user", "hello offline")])
    assert out.text
    assert out.usage.total_tokens >= 0


def test_t02_default_registry_is_fully_offline():
    # build_default_registry must not reach for Ollama at all.
    reg = build_default_registry()
    ids = {s.model.model_id for s in reg.available()}
    assert {"mock/fast", "mock/slow", "mock/raising", "mock/empty"} <= ids
