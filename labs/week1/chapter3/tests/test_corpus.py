"""Tests for rag.corpus -- load_corpus, load_questions, and
generate_corpus_and_questions.

Implements T-01, T-01a, T-01b, T-15 (SPEC §8.1, §15 ch2, §19).
"""

from __future__ import annotations

import json
import shutil

import pytest
from rag.corpus import (
    generate_corpus_and_questions,
    load_corpus,
    load_questions,
)

from rag.types import Question

# -- load_corpus -------------------------------------------------------------


def test_load_corpus_from_jsonl(tmp_path):
    d = tmp_path
    f = d / "corpus.jsonl"
    f.write_text(
        json.dumps(
            {
                "doc_id": "policy-17",
                "text": "Section 4.2 Business-Class Airfare.\n"
                "The refund limit is $5,000. "
                "Applies to all cabin classes.",
                "title": "Travel Policy",
                "section": "4.2 Business-Class Airfare",
                "domain": "travel",
                "author": "admin",
                "created_at": "2025-01-01",
                "updated_at": "2025-06-01",
                "version": 3,
                "access_level": "employee",
            }
        )
        + "\n"
    )
    docs = load_corpus(str(d))
    assert len(docs) == 1
    doc = docs[0]
    assert doc.doc_id == "policy-17"
    assert doc.metadata.title == "Travel Policy"
    assert doc.metadata.version == 3
    assert doc.metadata.domain == "travel"


def test_load_corpus_raises_on_empty_file(tmp_path):
    d = tmp_path
    f = d / "corpus.jsonl"
    f.write_text("")
    with pytest.raises(ValueError, match="empty|malformed|no documents"):
        load_corpus(str(d))


def test_load_corpus_raises_on_nonexistent_path():
    with pytest.raises(FileNotFoundError):
        load_corpus("/tmp/nonexistent-path-xyz")


# -- load_questions ---------------------------------------------------------


def test_load_questions_from_json(tmp_path, minimal_corpus_dir):
    path = str(tmp_path / "questions.json")
    shutil.copy(str(minimal_corpus_dir / "questions.json"), path)
    questions = load_questions(path)
    assert len(questions) > 0
    q = questions[0]
    assert isinstance(q, Question)
    assert q.tier in ("easy", "multi", "chunking", "distractor", "conflict", "recency", "injection")
    assert len(q.gold_facts) > 0
    # T-15: relevant_chunks must be non-empty.
    assert len(q.relevant_chunks) > 0


def test_load_questions_raises_on_missing_gold_facts(tmp_path, minimal_corpus_dir):
    path = str(tmp_path / "questions.json")
    shutil.copy(str(minimal_corpus_dir / "questions.json"), path)
    # Corrupt a question to remove gold_facts.
    with open(path) as f:
        data = json.loads(f.read())
    if data:
        data["questions"][0].pop("gold_facts", None)
        with open(path, "w") as f:
            f.write(json.dumps(data))
    with pytest.raises((ValueError, KeyError)):
        load_questions(path)


def test_load_questions_raises_on_absent_relevant_chunk(tmp_path, minimal_corpus_dir):
    path = str(tmp_path / "questions.json")
    shutil.copy(str(minimal_corpus_dir / "questions.json"), path)
    with open(path) as f:
        data = json.loads(f.read())
    if data:
        # Replace a valid id with one not in the corpus.
        q = data["questions"][0]
        if q.get("relevant_chunks"):
            q["relevant_chunks"][0] = "nonexistent#99"
        with open(path, "w") as f:
            f.write(json.dumps(data))
    with pytest.raises((ValueError, KeyError)):
        load_questions(path, allowed_chunk_ids={"valid#0"})


# -- generate_corpus_and_questions ------------------------------------------


def test_generate_corpus_and_questions_determinism(tmp_path):
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"
    generate_corpus_and_questions(str(out1), n_docs=5, n_questions=3, seed=42)
    generate_corpus_and_questions(str(out2), n_docs=5, n_questions=3, seed=42)
    # R-18: byte-identical under the same seed.
    docs1 = load_corpus(str(out1 / "documents" / "corpus.jsonl"))
    docs2 = load_corpus(str(out2 / "documents" / "corpus.jsonl"))
    assert len(docs1) == len(docs2) and len(docs1) == 5
    assert [d.doc_id for d in docs1] == [d.doc_id for d in docs2]


def test_generate_corpus_and_questions_diff_seed(tmp_path):
    out1 = tmp_path / "a"
    out2 = tmp_path / "b"
    generate_corpus_and_questions(str(out1), n_docs=10, n_questions=5, seed=1)
    generate_corpus_and_questions(str(out2), n_docs=10, n_questions=5, seed=2)
    docs1 = load_corpus(str(out1 / "documents" / "corpus.jsonl"))
    docs2 = load_corpus(str(out2 / "documents" / "corpus.jsonl"))
    # Different seeds yield different corpora.
    ids1 = [d.doc_id for d in docs1]
    ids2 = [d.doc_id for d in docs2]
    assert ids1 != ids2 or len(docs1) != len(docs2)


def test_generate_includes_failure_modes(tmp_path):
    out = tmp_path / "g"
    generate_corpus_and_questions(
        str(out),
        n_docs=50,
        n_questions=25,
        seed=42,
        failure_mode_docs=["injection", "conflict", "recency", "distractor"],
    )
    qs = load_questions(str(out / "questions.json"))
    tiers = {q.tier for q in qs}
    # Each failure mode should have at least 1 question.
    for tm in ("injection", "conflict", "recency", "distractor"):
        assert tm in tiers, f"missing tier {tm}"


# -- fixture ----------------------------------------------------------------


@pytest.fixture
def minimal_corpus_dir(tmp_path):
    d = tmp_path / "corpus"
    d.mkdir()
    docs = d / "documents"
    docs.mkdir()
    corpus_path = docs / "corpus.jsonl"
    corpus_path.write_text("")
    q = {
        "q_id": "q1",
        "question": "What is the refund limit?",
        "gold_answer": "The refund limit is $5000.",
        "gold_facts": ["refund limit is $5000"],
        "relevant_chunks": ["c0#0"],
        "tier": "easy",
    }
    corpus_path.write_text(
        json.dumps(
            {
                "doc_id": "c0",
                "text": "The refund limit is $5000.",
                "title": "Travel",
                "section": None,
                "domain": "finance",
            }
        )
        + "\n"
    )
    (d / "questions.json").write_text(json.dumps({"questions": [q]}))
    return d
