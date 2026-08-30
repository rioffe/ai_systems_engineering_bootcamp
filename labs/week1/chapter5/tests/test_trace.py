# pyright: reportMissingImports=false
from research_agent.trace import TraceRecorder


def test_trace_has_stable_id_and_typed_entries():
    recorder = TraceRecorder("q", "mock-policy", {"max_steps": 10})
    recorder.record_step(
        0,
        [
            {"kind": "reasoning", "text": "searching"},
            {"kind": "action", "tool": "search", "arguments": {"query": "q"}},
            {"kind": "observation", "tool": "search", "result": []},
        ],
    )
    recorder.record_termination(
        "goal_complete",
        1,
        2,
        0.000002,
        {
            "status": "insufficient_evidence",
            "answer": "limit",
            "citations": [],
            "conflicts": [],
            "caveats": [],
        },
    )
    artifact = recorder.to_artifact()
    assert artifact["agent_trace_version"] == "0.1"
    assert artifact["run_id"] == recorder.run_id
    assert {entry["kind"] for entry in artifact["steps"][0]["entries"]} == {
        "reasoning",
        "action",
        "observation",
    }
