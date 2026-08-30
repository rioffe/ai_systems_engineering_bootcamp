"""Deterministic Chapter 4 failure attribution."""

from __future__ import annotations

FAILURE_CLASSES = {
    "RETRIEVAL_FAILURE",
    "CONTEXT_FAILURE",
    "GENERATION_FAILURE",
    "PARSING_FAILURE",
    "EVALUATION_FAILURE",
}


def classify_failure(
    status: str,
    failure_stage: str | None,
    case_id: str,
    label_disagreements: set[str] | None = None,
) -> str | None:
    if status == "PASS":
        return None
    if status == "PARSE_BLOCKED":
        return "PARSING_FAILURE"
    if label_disagreements and case_id in label_disagreements:
        return "EVALUATION_FAILURE"
    if failure_stage in {"retrieval", "expansion", "reranking", "chunking"}:
        return "RETRIEVAL_FAILURE"
    if failure_stage == "context":
        return "CONTEXT_FAILURE"
    return "GENERATION_FAILURE"
