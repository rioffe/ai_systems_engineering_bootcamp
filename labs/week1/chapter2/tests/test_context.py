"""T-06 / T-06a / T-06b / E-05 / E-06 -- context construction + the token budget.

T-06 (I-004/I-006): ``build_context`` always respects the token budget (``tokens <=
budget``) and sets ``truncated`` iff any doc was dropped or cut.
T-06a (E-06): a two-doc dedupe of identical text keeps the highest-rank instance.
T-06b (I-005/I-006): the reported ``tokens`` is the ``est_tokens`` of the prompt that
was *actually* built (report ≡ build), and provenance order matches the docs order.
"""

from rag_eval.context import build_context, est_tokens
from rag_eval.types import Document, ScoredDoc


def _ranked(*pairs):
    # pairs of (doc_id, text, score); canonical order is score desc, document-id asc.
    scored = [
        ScoredDoc(Document(doc_id, text), score=s, rank=1) for doc_id, text, s in pairs
    ]
    scored.sort(key=lambda d: (-d.score, str(d.doc.doc_id)))
    for r, sd in enumerate(scored, start=1):
        sd.rank = r
    return scored


def test_est_tokens_ceil_over_four():
    assert est_tokens("") == 0
    assert est_tokens("abcd") == 1
    assert est_tokens("abcde") == 2
    assert est_tokens("a" * 100) == 25  # ceil(100/4)


def test_t06_budget_is_respected_and_report_equals_build():
    # I-006: for every budget, tokens is the est_tokens of the built prompt and <= budget.
    docs = _ranked(
        ("a", "word " * 40, 3.0), ("b", "word " * 40, 2.0), ("c", "short", 1.0)
    )
    for budget in (1, 2, 3, 5, 8, 16, 32, 128, 4000):
        ctx = build_context(docs, token_budget=budget)
        assert ctx.tokens <= budget, (budget, ctx.tokens)
        assert ctx.tokens == est_tokens(ctx.prompt)
    all_fit = build_context(docs, token_budget=4000)
    assert all_fit.truncated is False
    assert all_fit.tokens == est_tokens(all_fit.prompt)


def test_t06_budget_smaller_than_top_doc_truncates():
    # E-05: even a budget below the top doc yields a non-empty prompt, truncated, in budget.
    docs = _ranked(("only", "alpha beta gamma delta epsilon zeta eta", 5.0))
    ctx = build_context(docs, token_budget=2)
    assert ctx.tokens <= 2
    assert ctx.truncated is True
    assert ctx.prompt.strip() != ""  # non-empty prompt (E-05)


def test_t06_a_dedupe_keeps_highest_rank():
    # E-06: identical text keeps the highest-score (lowest-rank) instance; truncated=True.
    docs = [
        ScoredDoc(Document("a", "hello world"), score=5.0, rank=2),
        ScoredDoc(Document("b", "hello world"), score=9.0, rank=1),
    ]
    ctx = build_context(docs, token_budget=4000)
    assert [d.doc.doc_id for d in ctx.docs] == ["b"]
    assert ctx.truncated is True


def test_t06_b_provenance_matches_built_docs():
    # I-003/I-005/I-006: provenance equals the docs order; tokens is the builder's own.
    docs = _ranked(("001", "alpha", 3.0), ("002", "beta", 2.0), ("003", "gamma", 1.0))
    ctx = build_context(docs, token_budget=4000)
    assert ctx.provenance == [d.doc.doc_id for d in ctx.docs]
    assert len(ctx.provenance) == 3
    assert ctx.tokens == est_tokens(ctx.prompt)


def test_t06_budget_zero_is_empty_context():
    # budget 0: nothing can fit -> empty context; tokens never exceed the (zero) budget.
    docs = _ranked(("001", "alpha", 1.0))
    ctx = build_context(docs, token_budget=0)
    assert ctx.tokens == 0
    assert not ctx.provenance and ctx.docs == []
    assert ctx.empty


def test_t06_negative_budget_rejected():
    import pytest

    with pytest.raises(ValueError):
        build_context(_ranked(("x", "y", 1.0)), token_budget=-1)
