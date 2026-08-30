# pyright: reportMissingImports=false
from research_agent.metrics import compute_loop_metrics


def test_loop_metrics_count_calls_retries_denials_and_repairs():
    trace = {"steps": [{"entries": [
        {"kind": "action", "tool": "search", "arguments": {"query": "q"}},
        {"kind": "observation", "tool": "search", "error": "invalid_arguments", "attempt": 1},
        {"kind": "action", "tool": "search", "arguments": {"query": "q"}},
        {"kind": "observation", "tool": "search", "result": [], "attempt": 2},
    ]}], "termination": {"reason": "goal_complete", "tokens": 4, "cost_usd": 0.000004}}
    metrics = compute_loop_metrics(trace)
    assert metrics["search_calls"] == 2
    assert metrics["invalid_argument_count"] == 1
    assert metrics["repair_success"] == 1.0
    assert metrics["retry_count"] == 1
