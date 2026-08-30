"""Probabilistic policy boundary and deterministic MockPolicy."""
from __future__ import annotations

import json
from typing import Any, Protocol

import httpx

from .prompt import AGENT_PROMPT


class Policy(Protocol):
    def decide(self, state_view: dict[str, Any], tools: list[dict[str, Any]]) -> dict[str, Any]: ...

class MockPolicy:
    def __init__(self, fault: str | None = None):
        self.fault = fault
        self.used_fault = False

    def decide(self, state_view: dict[str, Any], tools: list[dict[str, Any]]) -> dict[str, Any]:
        observations = state_view.get("observations", [])
        if self.fault == "never_final":
            return {"type": "tool_call", "tool": "search", "arguments": {"query": f"{state_view['goal']} step-{len(observations)}"}}
        if self.fault in {"repeat_last_search", "repeat_search"}:
            return {"type": "tool_call", "tool": "search", "arguments": {"query": state_view["goal"]}}
        if self.fault == "retrieval_failure" and not self.used_fault:
            self.used_fault = True
            return {"type": "tool_call", "tool": "retrieve", "arguments": {"document_id": "missing-document"}}
        if self.fault == "attempt_delete" and not self.used_fault:
            self.used_fault = True
            return {"type": "tool_call", "tool": "delete_file", "arguments": {"path": "/tmp/sentinel"}}
        if self.fault == "null_query" and not self.used_fault:
            self.used_fault = True
            return {"type": "tool_call", "tool": "search", "arguments": {"query": None}}
        if self.fault == "retrieval_failure" and any(o.get("tool") == "retrieve" for o in observations):
            return {"type": "final", "report": {"status": "insufficient_evidence", "answer": "The requested information could not be verified from the available sources.", "citations": [], "conflicts": [], "caveats": []}}
        searches = [o for o in observations if o.get("tool") == "search" and o.get("result") is not None]
        if not searches:
            return {"type": "tool_call", "tool": "search", "arguments": {"query": state_view["goal"]}}
        hits = searches[-1].get("result") or []
        retrieves = [o for o in observations if o.get("tool") == "retrieve"]
        if hits and not retrieves:
            return {"type": "tool_call", "tool": "retrieve", "arguments": {"document_id": hits[0]["doc_id"]}}
        citations = [o["result"]["doc_id"] for o in retrieves if o.get("result") and isinstance(o["result"], dict)]
        return {"type": "final", "report": {"status": "ok" if citations else "insufficient_evidence", "answer": "The available evidence was reviewed." if citations else "The requested information could not be verified from the available sources.", "citations": citations, "conflicts": [], "caveats": []}}

class OllamaPolicy:
    def __init__(self, model: str = "qwen3.8:27b-mlx", endpoint: str = "http://localhost:11434"):
        self.model, self.endpoint = model, endpoint

    def decide(self, state_view: dict[str, Any], tools: list[dict[str, Any]]) -> dict[str, Any]:
        response = httpx.post(f"{self.endpoint}/api/chat", json={"model": self.model, "messages": [{"role": "system", "content": AGENT_PROMPT}, {"role": "user", "content": json.dumps(state_view, sort_keys=True)}], "stream": False}, timeout=30)
        response.raise_for_status()
        try:
            return json.loads(response.json()["message"]["content"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid policy response: {exc}") from exc


def resolve_policy(real: bool, model: str = "qwen3.8:27b-mlx") -> tuple[Policy, str, str, int]:
    if not real:
        return MockPolicy(), "DEGRADED_MOCK", "[REAL→MOCK] Ollama unreachable; running deterministic mock doubles", 0
    try:
        response = httpx.get("http://localhost:11434/api/tags", timeout=2)
        response.raise_for_status()
        names = {item.get("name") for item in response.json().get("models", [])}
        if model not in names:
            return MockPolicy(), "PULL_REQUIRED", f"MODEL_MISSING: run 'ollama pull {model}' — or pass --mock", 4
        return OllamaPolicy(model), "RUN_REAL", "", 0
    except httpx.HTTPError:
        return MockPolicy(), "DEGRADED_MOCK", "[REAL→MOCK] Ollama unreachable; running deterministic mock doubles", 0
