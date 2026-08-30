# pyright: reportMissingImports=false

import json

from rag_eval.dataset import (
    CATEGORY_SET,
    Dataset,
    EvalCase,
    load_dataset,
    validate_dataset,
)


def case(case_id="q-1", **overrides):
    value = {
        "case_id": case_id,
        "question": "What is the answer?",
        "reference_answer": "The answer is yes.",
        "relevant_chunks": ["doc#0"],
        "category": "easy",
        "gold_facts": ["yes"],
    }
    value.update(overrides)
    return value


def write_dataset(tmp_path, cases):
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps({"dataset_id": "golden-v1", "cases": cases}))
    return path


def test_valid_dataset_loads_and_preserves_order(tmp_path):
    path = write_dataset(tmp_path, [case("q-1"), case("q-2", difficulty="hard")])
    dataset = load_dataset(path, corpus_ids={"doc#0"})
    assert dataset.dataset_id == "golden-v1"
    assert [item.case_id for item in dataset.cases] == ["q-1", "q-2"]
    assert dataset.cases[1].difficulty == "hard"


def test_validation_enumerates_duplicate_category_reference_and_sentinel(tmp_path):
    path = write_dataset(
        tmp_path,
        [
            case("same"),
            case("same", category="not-a-category", relevant_chunks=["missing"], reference_answer="REPLACE_ME"),
        ],
    )
    report = validate_dataset(load_dataset(path, corpus_ids={"doc#0"}, validate=False), corpus_ids={"doc#0"})
    messages = " ".join(report)
    assert "duplicate case_id" in messages
    assert "category" in messages
    assert "missing" in messages
    assert "REPLACE_ME" in messages


def test_strict_mode_enforces_floor_but_default_does_not(tmp_path):
    path = write_dataset(tmp_path, [case()])
    assert load_dataset(path, corpus_ids={"doc#0"}).dataset_id == "golden-v1"
    try:
        load_dataset(path, corpus_ids={"doc#0"}, strict=True)
    except ValueError as exc:
        assert "50" in str(exc)
    else:
        raise AssertionError("strict mode must reject fewer than 50 cases")


def test_malformed_json_is_a_deterministic_error(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{")
    try:
        load_dataset(path)
    except ValueError as exc:
        assert "JSON" in str(exc)
    else:
        raise AssertionError("malformed JSON must fail")


def test_category_set_is_closed():
    assert {"easy", "regression", "injection"}.issubset(CATEGORY_SET)
    assert isinstance(EvalCase, type)
    assert isinstance(Dataset, type)
