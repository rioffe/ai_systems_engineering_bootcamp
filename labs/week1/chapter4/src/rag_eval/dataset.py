"""Golden evaluation dataset types and deterministic validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CATEGORY_SET = {
    "easy",
    "multi",
    "chunking",
    "distractor",
    "conflict",
    "recency",
    "injection",
    "adversarial",
    "boundary",
    "regression",
}


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    question: str
    reference_answer: str
    relevant_chunks: list[str]
    category: str
    gold_facts: list[str]
    difficulty: str | None = None
    source: str = "golden"


@dataclass(frozen=True)
class Dataset:
    dataset_id: str
    cases: list[EvalCase]


def _case(raw: dict[str, Any], index: int) -> EvalCase:
    required = (
        "case_id",
        "question",
        "reference_answer",
        "relevant_chunks",
        "category",
        "gold_facts",
    )
    missing = [key for key in required if key not in raw]
    if missing:
        raise ValueError(f"case {index}: missing required fields: {', '.join(missing)}")
    return EvalCase(
        case_id=str(raw["case_id"]),
        question=str(raw["question"]),
        reference_answer=str(raw["reference_answer"]),
        relevant_chunks=list(raw["relevant_chunks"]),
        category=str(raw["category"]),
        gold_facts=list(raw["gold_facts"]),
        difficulty=raw.get("difficulty"),
        source=str(raw.get("source", "golden")),
    )


def _raw_document(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"JSON dataset error: {exc}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("cases"), list):
        raise TypeError("JSON dataset error: expected an object with a cases array")
    if not isinstance(document.get("dataset_id"), str) or not document["dataset_id"]:
        raise ValueError("JSON dataset error: dataset_id must be a non-empty string")
    return document


def load_dataset(
    path: str | Path,
    corpus_ids: set[str] | None = None,
    strict: bool = False,
    *,
    validate: bool = True,
) -> Dataset:
    document = _raw_document(Path(path))
    try:
        cases = [_case(raw, index) for index, raw in enumerate(document["cases"])]
    except (TypeError, ValueError) as exc:
        raise ValueError(str(exc)) from exc
    dataset = Dataset(document["dataset_id"], cases)
    if validate:
        violations = validate_dataset(dataset, corpus_ids=corpus_ids, strict=strict)
        if violations:
            raise ValueError("dataset violations: " + "; ".join(violations))
    return dataset


def validate_dataset(
    dataset: Dataset,
    corpus_ids: set[str] | None = None,
    strict: bool = False,
) -> list[str]:
    violations: list[str] = []
    if strict and len(dataset.cases) < 50:
        violations.append(
            f"strict dataset floor requires at least 50 cases, got {len(dataset.cases)}"
        )
    seen: set[str] = set()
    for index, item in enumerate(dataset.cases):
        if item.case_id in seen:
            violations.append(f"case {index}: duplicate case_id {item.case_id}")
        seen.add(item.case_id)
        if item.category not in CATEGORY_SET:
            violations.append(f"case {item.case_id}: invalid category {item.category}")
        if corpus_ids is not None:
            for chunk_id in item.relevant_chunks:
                if chunk_id not in corpus_ids:
                    violations.append(f"case {item.case_id}: missing corpus chunk {chunk_id}")
        fields = (item.question, item.reference_answer, *item.relevant_chunks, *item.gold_facts)
        if any(value == "REPLACE_ME" for value in fields):
            violations.append(f"case {item.case_id}: REPLACE_ME sentinel is not valid golden data")
    return violations
