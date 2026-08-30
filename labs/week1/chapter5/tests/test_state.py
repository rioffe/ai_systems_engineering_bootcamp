# pyright: reportMissingImports=false
from research_agent.state import (
    AgentState,
    canonical_action,
    canonical_json,
    surrogate_latency_ms,
    surrogate_tokens,
)


def test_state_and_surrogates_are_deterministic():
    entry = {"kind": "action", "tool": "search", "arguments": {"query": "q"}}
    assert canonical_json(entry) == '{"arguments":{"query":"q"},"kind":"action","tool":"search"}'
    assert canonical_action("search", {"query": "q"})
    assert surrogate_tokens(entry) > 0
    assert surrogate_latency_ms(entry) == surrogate_latency_ms(entry)
    assert AgentState("q").view()["goal"] == "q"
