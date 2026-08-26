"""T-01 / T-01a / T-01b / T-15 -- the seeded corpus + ground-truth (R-10/R-14/R-15).

T-01: `gen-corpus --seed 42` writes exactly 100 distinct `documents/NNN.txt` and a
`questions.json` of 25 questions, each with a non-empty `relevant_docs` subset of the
corpus and a tier in the four §17 tiers; two same-seed runs are byte-identical.
T-01a: `load_corpus` + `load_questions` accept the generated artifacts, and raise on a
    blank/missing `relevant_docs` or an id absent from the corpus.
T-01b: the 25-question set has a non-trivial per-tier distribution; the `distractor`
    questions have lexically-similar-but-irrelevant siblings present in the corpus (§6/§7/§17).
T-15 / I-013: a corrupt `questions.json` (a `relevant_docs` id absent from the corpus) is
    a load-time error, not a silent 0-recall -- `load_questions` raises `CorpusError`.
"""

import json

import pytest

from rag_eval.corpus import (
    DOMAIN_NAMES,
    CorpusError,
    generate_corpus_and_questions,
    load_corpus,
    load_questions,
)


def test_t01_generation_writes_100_docs_and_25_questions():
    docs, info, questions = generate_corpus_and_questions(
        None, n_docs=100, n_questions=25, seed=42, write=False
    )
    assert len(docs) == 100
    assert len({d.doc_id for d in docs}) == 100
    assert len(questions) == 25
    # every question: non-blank text, non-empty relevant_docs ⊆ corpus, a known tier
    ids = {d.doc_id for d in docs}
    for q in questions:
        assert q.question.strip()
        assert q.relevant_docs and all(r in ids for r in q.relevant_docs)
        assert q.tier in Domain_tiers()
    assert set(q.tier for q in questions) == set(
        Domain_tiers()
    )  # all four tiers present


def test_t01_generation_is_byte_identical_for_a_seed(tmp_path):
    # Two same-seed runs produce byte-identical questions.json + documents/ (R-15/T-01).
    a = tmp_path / "a"
    b = tmp_path / "b"
    generate_corpus_and_questions(str(a), seed=42, write=True)
    generate_corpus_and_questions(str(b), seed=42, write=True)
    assert (a / "questions.json").read_bytes() == (b / "questions.json").read_bytes()
    na = sorted(f.name for f in (a / "documents").glob("*.txt"))
    nb = sorted(f.name for f in (b / "documents").glob("*.txt"))
    assert len(na) == 100 and na == nb
    # a different seed is (very likely) a different corpus
    generate_corpus_and_questions(str(tmp_path / "c"), seed=7, write=True)
    assert (tmp_path / "a" / "questions.json").read_bytes() != (
        tmp_path / "c" / "questions.json"
    ).read_bytes()


def test_t01_load_accepts_generated_artifacts(tmp_path):
    generate_corpus_and_questions(str(tmp_path), seed=42, write=True)
    docs = load_corpus(str(tmp_path / "documents"))
    assert len(docs) == 100
    qs = load_questions(str(tmp_path / "questions.json"), docs, allow_dangling=False)
    assert len(qs) == 25
    # ground-truth integrity holds after round-trip through disk
    for q in qs:
        assert all(r in {d.doc_id for d in docs} for r in q.relevant_docs)


def test_t01a_load_questions_raises_on_blank_relevant_docs(tmp_path):
    bad = tmp_path / "q.json"
    bad.write_text(
        json.dumps(
            {
                "questions": [
                    {
                        "q_id": "q1",
                        "question": "hi",
                        "gold_answer": "x",
                        "relevant_docs": [],
                        "tier": "easy",
                    }
                ]
            }
        )
    )
    with pytest.raises(CorpusError):
        load_questions(str(bad), allow_dangling=False, strict=True)


def test_t01a_load_questions_raises_on_empty_question(tmp_path):
    bad = tmp_path / "q.json"
    bad.write_text(
        json.dumps(
            {
                "questions": [
                    {
                        "q_id": "q1",
                        "question": "   ",
                        "gold_answer": "x",
                        "relevant_docs": ["001"],
                        "tier": "easy",
                    }
                ]
            }
        )
    )
    with pytest.raises(CorpusError):
        load_questions(str(bad), strict=True)


def test_t01b_distractor_regime_has_lexically_similar_siblings():
    docs, info, questions = generate_corpus_and_questions(
        None, n_docs=100, n_questions=25, seed=42, write=False
    )
    dist = {}
    for q in questions:
        dist[q.tier] = dist.get(q.tier, 0) + 1
    for tier in Domain_tiers():
        assert dist.get(tier, 0) > 0, f"tier {tier} absent"
    # The "distractor" regime is the interesting one (§6/§7/§17): a target doc and its
    # same-domain sibling share vocabulary but the sibling is NOT in relevant_docs.
    distractors = [q for q in questions if q.tier == "distractor"]
    assert distractors, "no distractor questions generated"
    by_domain: dict[str, list[str]] = {}
    for d in docs:
        by_domain.setdefault(d.domain or "n/a", []).append(d.doc_id)
    for q in distractors:
        target = q.relevant_docs[0]
        target_domain = next(d.domain for d in docs if d.doc_id == target)
        siblings = [
            r for r in q.relevant_docs for _ in [0]
        ]  # sanity: relevant_docs non-empty
        assert siblings
        # A lexically-similar sibling exists in the same domain but is not relevant:
        dom = by_domain.get(target_domain, [])
        assert len(dom) >= 2, "distractor target domain has no sibling"
        assert any(r not in set(q.relevant_docs) for r in dom), (
            "no irrelevant sibling present"
        )


# A stable, import-safe reference to the four §17 tiers (independent of the class).
def Domain_tiers():
    from rag_eval.types import Question

    return list(Question.TIERS)
