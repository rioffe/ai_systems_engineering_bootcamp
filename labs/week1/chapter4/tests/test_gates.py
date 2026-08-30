# pyright: reportMissingImports=false

from rag_eval.gates import evaluate_gates, gate_exit_code


def test_gates_pass_and_fail_closed():
    report = {"metrics": {"accuracy": {"baseline": 0.9, "current": 0.895, "delta": -0.005}, "latency_p95": {"baseline": 100, "current": 110, "delta": -10}}}
    passing = evaluate_gates(report, {"version": 1, "gates": [{"metric": "accuracy", "constraint": "drop", "max_pct_points": 1.0}]})
    assert gate_exit_code(passing) == 0
    missing = evaluate_gates({"metrics": {}}, {"version": 1, "gates": [{"metric": "accuracy", "constraint": "drop", "max_pct_points": 1.0}]})
    assert gate_exit_code(missing) == 1
    assert missing["gates"][0]["reason"] == "missing-metric"
