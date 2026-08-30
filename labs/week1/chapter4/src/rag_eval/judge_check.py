"""Validate judge verdicts against human labels."""
from __future__ import annotations

FIELDS = ("correct", "supported", "complete")


def judge_check(eval_artifact: dict, labels: dict) -> dict:
    if not labels:
        return {"status": "NO_LABELS", "agreement": {}, "disagreements": []}
    disagreements = []
    counts = {field: [0, 0] for field in FIELDS}
    rows = {row.get("case_id"): row for row in eval_artifact.get("cases", [])}
    for case_id, label in labels.items():
        verdict = rows.get(case_id, {}).get("verdict", {})
        for field in FIELDS:
            if field in label:
                counts[field][1] += 1
                if verdict.get(field) == label[field]:
                    counts[field][0] += 1
                else:
                    disagreements.append({"case_id": case_id, "field": field, "judge": verdict.get(field), "human": label[field]})
    return {"status": "OK", "agreement": {field: (good / total if total else None) for field, (good, total) in counts.items()}, "disagreements": disagreements}
