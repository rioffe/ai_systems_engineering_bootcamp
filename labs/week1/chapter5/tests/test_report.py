# pyright: reportMissingImports=false
from research_agent.report import load_trace, write_trace


def test_trace_round_trip(tmp_path):
    artifact = {
        "agent_trace_version": "0.1",
        "run_id": "abc",
        "question": "q",
        "model": "mock-policy",
        "model_params": {},
        "prompt_version": "agent-prompt-v1",
        "usage_kind": "synthetic",
        "steps": [],
        "termination": {"reason": "max_steps"},
        "report": {},
        "loop_metrics": {},
    }
    path = tmp_path / "trace.json"
    write_trace(path, artifact)
    assert load_trace(path)["run_id"] == "abc"
