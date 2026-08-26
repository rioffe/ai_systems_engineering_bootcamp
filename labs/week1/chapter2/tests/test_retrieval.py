"""T-04 / T-05c -- BM25 retrieval: determinism, tie-break, and ranking sanity.

T-04 (I-002): for a fixed corpus + query + (k1,b,tokenizer) the BM25 list is byte
identical across two builds; equal scores resolve by document-id ascending.
T-05c: on the seeded corpus, easy/multi questions reach recall = 1.0 (the retrieved
top-k contains the relevant docs); the distractor regime is "allowed to miss" but
*never crashes* and never yields inf/nan.
"""

from rag_eval.metrics import retrieval_pr
from rag_eval.retrieval import BM25Retriever, tokenize
from rag_eval.types import Document, ScoredDoc


def _docs(*pairs):
    return [Document(doc_id=i, text=t) for i, t in pairs]


def _ranked(*pairs):
    # pairs of (doc_id, text, score); canonical order is score desc, document-id asc.
    out = [ScoredDoc(Document(i, t), score=s, rank=1) for i, t, s in pairs]
    out.sort(key=lambda d: (-d.score, str(d.doc.doc_id)))
    for r, sd in enumerate(out, start=1):
        sd.rank = r
    return out


def test_t04_tokenizer_determinism_and_keep_numbers():
    r1 = tokenize("The Quick-Brown Fox 42 Jumps", keep_numbers=True)
    r2 = tokenize("The Quick-Brown Fox 42 Jumps", keep_numbers=True)
    assert r1 == r2
    assert "42" in r1  # numbers kept
    assert all(t for t in r1)  # no empty tokens
    no_num = tokenize("The 42 Fox", keep_numbers=False)
    assert "42" not in no_num


def test_t04_search_deterministic_across_two_builds():
    corpus = _docs(
        ("a", "alpha beta gamma"), ("b", "beta gamma delta"), ("c", "alpha delta")
    )
    r1 = [sd.doc.doc_id for sd in BM25Retriever(corpus).search("alpha gamma", 3)]
    r2 = [sd.doc.doc_id for sd in BM25Retriever(corpus).search("alpha gamma", 3)]
    assert r1 == r2


def test_t04_tie_break_is_doc_id_ascending():
    # Two docs with identical text yield identical scores; document-id asc breaks the tie.
    corpus = _docs(("003", "the same text here"), ("001", "the same text here"))
    scored = BM25Retriever(corpus).search("same text", 5)
    assert len(scored) == 2
    assert all(abs(a.score - b.score) < 1e-9 for a, b in zip(scored, scored[1:]))
    assert [sd.doc.doc_id for sd in scored] == ["001", "003"]


def test_t05_search_k_limits_and_empty():
    corpus = _docs(
        ("001", "apple orange"),
        ("002", "banana orange"),
        ("003", "cherry"),
    )
    got = BM25Retriever(corpus).search("orange", k=1)
    assert len(got) == 1
    assert BM25Retriever(corpus).search("nonexistent-xyz", 5) == []  # no matches
    assert BM25Retriever(corpus).search("orange", 0) == []  # k <= 0
    assert BM25Retriever([]).search("orange", 5) == []  # E-02: empty corpus


def test_t05c_easy_and_multi_recall_is_one(corpus):
    # `corpus` (conftest) is the seeded 100-doc / 25-question dataset + its retriever.
    _docs, _info, questions, retr = corpus
    for tier in ("easy", "multi"):
        tier_q = [q for q in questions if q.tier == tier]
        recalls = []
        for q in tier_q:
            retrieved = [sd.doc.doc_id for sd in retr.search(q.question, 5)]
            _, _, _, _, recall, _ = retrieval_pr(q.relevant_docs, retrieved)
            recalls.append(recall)
        assert recalls, f"no questions in tier {tier}"
        assert all((r or 0.0) == 1.0 for r in recalls), (tier, recalls)


def test_t05c_distractor_allowed_to_miss_but_never_crashes(corpus):
    _docs, _info, questions, retr = corpus
    any_miss = False
    any_hit = False
    for q in questions:
        if q.tier != "distractor":
            continue
        retrieved = [sd.doc.doc_id for sd in retr.search(q.question, 5)]
        tp, fp, fn, p, r, f1 = retrieval_pr(q.relevant_docs, retrieved)
        assert tp + fn == len(q.relevant_docs), (
            "TP+FN must equal the relevant-doc universe"
        )
        assert f1 == 0.0 or 0.0 <= f1 <= 1.0  # no inf/nan (I-007)
        assert p is None or 0.0 <= p <= 1.0
        assert r is None or 0.0 <= r <= 1.0
        if (r or 0.0) < 1.0:
            any_miss = True
        if tp > 0:
            any_hit = True
    # The distractor regime is "allowed to miss" but exercises retrieval without crashing.
    assert any_hit, "at least one distractor question should retrieve its target"
