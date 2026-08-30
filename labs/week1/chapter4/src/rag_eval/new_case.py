"""Production trace to incomplete golden-case scaffold."""

from __future__ import annotations


def scaffold_case(trace: dict, case_id: str) -> dict:
    return {
        "case_id": case_id,
        "question": trace.get("question", ""),
        "reference_answer": "REPLACE_ME",
        "relevant_chunks": ["REPLACE_ME"],
        "category": "production",
        "gold_facts": ["REPLACE_ME"],
        "source": "production",
    }
