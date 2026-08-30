# pyright: reportMissingImports=false

from rag_eval.compare import compare_artifacts


def make(accuracy, latency=10):
    return {
        "eval_report_version": "0.1",
        "dataset_id": "x",
        "usage_kind": "synthetic",
        "aggregate": {
            "accuracy": accuracy,
            "latency_p95": latency,
            "by_category": {"easy": {"accuracy": accuracy}},
        },
    }


def test_directional_delta_and_dataset_guard():
    report = compare_artifacts(make(0.9, 10), make(0.8, 12))
    assert report["metrics"]["accuracy"]["delta"] == -0.1
    assert report["metrics"]["latency_p95"]["delta"] == -2
    try:
        compare_artifacts(make(0.9), {**make(0.8), "dataset_id": "other"})
    except ValueError as exc:
        assert "dataset_id" in str(exc)
    else:
        raise AssertionError("dataset mismatch must fail")
