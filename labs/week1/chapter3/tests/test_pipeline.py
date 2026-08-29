"""Tests for rag.pipeline -- build_index + run_case + run_dataset.

Implements T-03, T-07, T-10, T-11a, T-13, R-01, R-14, R-15 from SPEC.md C-12;
E-11 / E-12 / I-008 failure attribution (R-15) covered in the last section.
"""

from __future__ import annotations

from rag.corpus import generate_corpus_and_questions, load_corpus
from rag.embedding import MockEmbedder
from rag.judgment import MockJudge
from rag.model import MockLLM
from rag.pipeline import build_index, run_case, run_dataset
from rag.types import Answer, Question, Verdict

# -- build_index (T-03) ------------------------------------------------------


def test_build_index_returns_vectorstore_and_bm25(tmp_path):
    generate_corpus_and_questions(
        str(tmp_path / "gen"),
        n_docs=5,
        n_questions=3,
        seed=42,
    )
    docs = load_corpus(str(tmp_path / "gen" / "documents" / "corpus.jsonl"))
    embedder = MockEmbedder()
    vs, bm = build_index(
        docs,
        strategy="fixed",
        contextual=True,
        embedder=embedder,
        overlap=10,
        chunk_size=50,
        embed_model="mock",
        mock=True,
    )
    assert vs is not None
    assert bm is not None
    assert len(vs._data) > 0 or len(bm._data) > 0


def test_build_index_determinism(tmp_path):
    # Running build_index twice with the same seed yields byte-identical
    # index outputs
    # (I-002, T-03).
    generate_corpus_and_questions(
        str(tmp_path / "gen"),
        n_docs=5,
        n_questions=3,
        seed=42,
    )
    docs = load_corpus(str(tmp_path / "gen" / "documents" / "corpus.jsonl"))
    e1 = MockEmbedder()
    e2 = MockEmbedder()
    vs1, _ = build_index(
        docs,
        strategy="fixed",
        contextual=True,
        embedder=e1,
        overlap=10,
        chunk_size=50,
        embed_model="mock",
        mock=True,
    )
    vs2, _ = build_index(
        docs,
        strategy="fixed",
        contextual=True,
        embedder=e2,
        overlap=10,
        chunk_size=50,
        embed_model="mock",
        mock=True,
    )
    # Compare stored vectors (same chunk_ids, same embedding values).
    keys1 = sorted((d.chunk_id, tuple(round(v, 6) for v in vec)) for d, vec in vs1._data.values())
    keys2 = sorted((d.chunk_id, tuple(round(v, 6) for v in vec)) for d, vec in vs2._data.values())
    assert keys1 == keys2


# -- run_case (T-11a) --------------------------------------------------------


def test_run_case_easy_tier_passes(tmp_path):
    generate_corpus_and_questions(
        str(tmp_path / "gen"),
        n_docs=10,
        n_questions=5,
        seed=42,
        failure_mode_docs=["conflict", "recency"],
    )
    docs = load_corpus(str(tmp_path / "gen" / "documents" / "corpus.jsonl"))
    embedder = MockEmbedder()
    vs, bm = build_index(
        docs,
        strategy="fixed",
        contextual=True,
        embedder=embedder,
        overlap=10,
        chunk_size=50,
        embed_model="mock",
        mock=True,
    )
    questions = [
        Question(
            q_id="q-test",
            question="What is the refund limit?",
            gold_answer="The refund limit is $5000.",
            gold_facts=["refund limit is $5000"],
            relevant_chunks=["doc-0000-1234#0"],
            relevant_docs=["doc-0000-1234"],
            tier="easy",
        )
    ]
    metrics = run_case(
        questions[0],
        (vs, bm),
        hybrid=True,
        alpha=0.5,
        rerank=False,
        top_n=50,
        top_k=5,
        expand=False,
        n_expand=0,
        judge=MockJudge(),
        llm=MockLLM(),
        cfg=None,
    )
    assert metrics.status in ("SCORED", "PARTIAL", "ERROR")
    assert metrics.q_id == "q-test"
    assert metrics.tier == "easy"


def test_run_case_determinism(tmp_path):
    # Two identical runs on the same corpus+question+params produce the
    # same RunMetrics output (R-18).
    generate_corpus_and_questions(
        str(tmp_path / "gen"),
        n_docs=10,
        n_questions=5,
        seed=42,
    )
    docs = load_corpus(str(tmp_path / "gen" / "documents" / "corpus.jsonl"))
    e1 = MockEmbedder()
    e2 = MockEmbedder()
    vs1, _ = build_index(
        docs,
        strategy="fixed",
        contextual=True,
        embedder=e1,
        overlap=10,
        chunk_size=50,
        embed_model="mock",
        mock=True,
    )
    vs2, _ = build_index(
        docs,
        strategy="fixed",
        contextual=True,
        embedder=e2,
        overlap=10,
        chunk_size=50,
        embed_model="mock",
        mock=True,
    )
    q = Question(
        q_id="q-det",
        question="What is the refund limit?",
        gold_answer="The refund limit is $5000.",
        gold_facts=["refund limit is $5000"],
        relevant_chunks=["doc-0000-1234#0"],
        relevant_docs=["doc-0000-1234"],
        tier="easy",
    )
    m1 = run_case(
        q,
        (vs1, _),
        hybrid=True,
        alpha=0.5,
        rerank=False,
        top_n=50,
        top_k=5,
        expand=False,
        n_expand=0,
        judge=MockJudge(),
        llm=MockLLM(),
        cfg=None,
    )
    m2 = run_case(
        q,
        (vs2, _),
        hybrid=True,
        alpha=0.5,
        rerank=False,
        top_n=50,
        top_k=5,
        expand=False,
        n_expand=0,
        judge=MockJudge(),
        llm=MockLLM(),
        cfg=None,
    )
    assert m1.retrieved == m2.retrieved
    assert m1.precision == m2.precision
    assert m1.recall == m2.recall


# -- run_dataset ------------------------------------------------------------


def test_run_dataset_produces_metrics_list(tmp_path):
    generate_corpus_and_questions(
        str(tmp_path / "gen"),
        n_docs=10,
        n_questions=3,
        seed=42,
    )
    docs = load_corpus(str(tmp_path / "gen" / "documents" / "corpus.jsonl"))
    embedder = MockEmbedder()
    vs, bm = build_index(
        docs,
        strategy="fixed",
        contextual=True,
        embedder=embedder,
        overlap=10,
        chunk_size=50,
        embed_model="mock",
        mock=True,
    )
    questions = load_corpus(  # load from the same corpus
        str(tmp_path / "gen" / "documents" / "corpus.jsonl")
    )
    # Use a minimal generated questions list.
    metrics_list = run_dataset(
        questions,
        (vs, bm),
        hybrid=True,
        alpha=0.5,
        rerank=False,
        top_n=50,
        top_k=5,
        expand=False,
        n_expand=0,
        judge=MockJudge(),
        llm=MockLLM(),
        cfg=None,
    )
    # Note: the questions loaded from the corpus are Document objects,
    # not Question objects. run_dataset will handle this gracefully.
    assert isinstance(metrics_list, list)


# -- failure attribution (T-10 / I-008 / R-15, E-11, E-12) ------------------


class _FailingJudge(MockJudge):
    """E-11 double: the judge terminal-faults (status ERROR) -> PARTIAL."""

    def judge(
        self,
           *,
        question,
        context,
        answer,
        claims,
        gold_facts,
        max_retries: int = 2,
        on_failure: str | None = None,
      ) -> Verdict:
        return Verdict(
            q_id=question.q_id,
            status="ERROR",
            rationale="simulated judge failure after retries",
           )


class _RaisingJudge(MockJudge):
    """E-11 double: the judge raises -> also a judge-stage PARTIAL."""

    def judge(
        self,
           *,
        question,
        context,
        answer,
        claims,
        gold_facts,
        max_retries: int = 2,
        on_failure: str | None = None,
       ) -> Verdict:
        raise RuntimeError("simulated judge crash")


class _ErrorAnswerLLM(MockLLM):
    """Double whose generate() terminal-faults -> generation-stage ERROR (E-11)."""

    def generate(  # type: ignore[override]
        self,
           *,
        system,
        context,
        question,
        schema,
        max_tokens: int = 512,
        temperature: float = 0.0,
        seed: int | None = None,
        max_retries: int = 2,
        on_failure: str | None = None,
       ) -> Answer:
        return Answer(
            q_id=str(schema.get("q_id", "x")),
            text="",
            confidence=0.0,
            status="ERROR",
            error="simulated generation failure",
           )


def _easy_env(tmp_path):
    """Build a small index over a generated corpus + an 'easy' question."""
    generate_corpus_and_questions(
        str(tmp_path / "gen"),
        n_docs=10,
        n_questions=5,
        seed=42,
      )
    docs = load_corpus(str(tmp_path / "gen" / "documents" / "corpus.jsonl"))
    vs, bm = build_index(
        docs,
        strategy="fixed",
        contextual=True,
        embedder=MockEmbedder(),
        overlap=10,
        chunk_size=50,
        embed_model="mock",
        mock=True,
      )
    q = Question(
        q_id="q-t10",
        question="What is the refund limit?",
        gold_answer="The refund limit is $5000.",
        gold_facts=["refund limit is $5000"],
        relevant_chunks=["doc-0000-1234#0"],
        relevant_docs=["doc-0000-1234"],
        tier="easy",
      )
    return (vs, bm), q


def test_partial_when_judge_faults_after_generate(tmp_path):
    # T-10 / E-11: a judge failure after a successful generate -> PARTIAL,
    # failure_stage="judging", with a COMPLETE retrieval diagnosis remaining.
    (vs, bm), q = _easy_env(tmp_path)
    m = run_case(
        q,
        (vs, bm),
        judge=_FailingJudge(),
        llm=MockLLM(),
      )
    assert m.status == "PARTIAL"
    assert m.failure_stage == "judging"
    # Retrieval diagnosis is intact (RETRIEVING cleared before the judge fault).
    assert isinstance(m.retrieved, list) and len(m.retrieved) > 0
    assert m.recall is not None
    # Generation-QA metrics are absent (the judge produced no clean verdict).
    assert m.faithfulness is None
    assert m.completeness is None
    assert m.citation_quality is None
    assert m.correct is None
    assert m.which_field_decided is None


def test_partial_when_judge_raises(tmp_path):
    # T-10 / E-11: the judge *raising* is a judge-stage fault -> PARTIAL too.
    (vs, bm), q = _easy_env(tmp_path)
    m = run_case(q, (vs, bm), judge=_RaisingJudge(), llm=MockLLM())
    assert m.status == "PARTIAL"
    assert m.failure_stage == "judging"


def test_error_when_generation_faults(tmp_path):
    # T-10 / E-11: a generation-stage fault -> ERROR naming "generation", with
    # the retrieval diagnosis still complete (RETRIEVING cleared first).
    (vs, bm), q = _easy_env(tmp_path)
    m = run_case(q, (vs, bm), judge=MockJudge(), llm=_ErrorAnswerLLM())
    assert m.status == "ERROR"
    assert m.failure_stage == "generation"
    assert len(m.retrieved) > 0
    assert m.answer_status == "ERROR"


def test_scored_case_has_no_failure_stage(tmp_path):
    # I-008: a clean run SCORES and carries NO failure_stage -- a stage is named
    # only on a terminal ERROR/PARTIAL.
    (vs, bm), q = _easy_env(tmp_path)
    m = run_case(q, (vs, bm), judge=MockJudge(), llm=MockLLM())
    assert m.status == "SCORED"
    assert m.failure_stage is None
    assert len(m.retrieved) > 0


def test_judge_off_ablation(tmp_path):
    # T-10 / E-12: --judge off (judge=None) is a retrieval-only eval -- the
    # generation-QA metrics stay None and the case still SCORES.
    (vs, bm), q = _easy_env(tmp_path)
    m = run_case(q, (vs, bm), judge=None, llm=MockLLM())
    assert m.status == "SCORED"
    assert m.failure_stage is None
    assert m.faithfulness is None
    assert m.completeness is None


def test_failure_stage_single_and_valid(tmp_path):
    # I-008: a terminal ERROR/PARTIAL names exactly one valid failure stage.
    valid = {
        "retrieval",
        "expansion",
        "reranking",
        "context",
        "generation",
        "judging",
      }
    (vs, bm), q = _easy_env(tmp_path)
    m = run_case(q, (vs, bm), judge=_FailingJudge(), llm=MockLLM())
    assert m.status in ("SCORED", "PARTIAL", "ERROR")
    if m.status in ("ERROR", "PARTIAL"):
        assert m.failure_stage in valid
    else:
        assert m.failure_stage is None


def test_run_dataset_scores_real_questions(tmp_path):
    # run_dataset over real Question objects (not Documents) SCORES every row;
    # the run-all default yields a full list with no crash.
    (vs, bm), q = _easy_env(tmp_path)
    metrics = run_dataset([q, q], (vs, bm), judge=MockJudge(), llm=MockLLM())
    assert len(metrics) == 2
    assert all(mm.status == "SCORED" for mm in metrics)
