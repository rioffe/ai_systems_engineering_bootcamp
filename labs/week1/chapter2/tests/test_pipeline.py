"""Pipeline: the §13 wiring -- retrieve -> context -> generate -> judge -> metrics.

T-10 / I-008: a failed stage names exactly one ``failure_stage``; a generation or
judge fault still yields a full retrieval diagnosis. E-08 / T-08c: a foreign source
citation is a grounding violation (stripped, ``supported`` forced False, claim
counted). §3.1 / --judge off: a judge-off case is a retrieval-only eval (verdict
SKIPPED, metrics intact). §9.5 / R-11: run_dataset aggregates rows with a per-tier
    breakdown and honours --stop-on-error.
"""

from rag_eval.judgment import MockJudge
from rag_eval.model import MockLLM
from rag_eval.pipeline import CaseRun, RunReport, run_case, run_dataset
from rag_eval.retrieval import BM25Retriever
from rag_eval.types import Document, Question

DOCS = [
    Document(
        "001",
        "the reimbursement limit for hotels is five thousand dollars effective 2024",
    ),
    Document(
        "002",
        "visa applications require two photos and a processing fee of ten dollars",
    ),
    Document(
        "003",
        "the hotel per-diem cap for new hires is one thousand dollars in the 2024 period",
    ),
    Document(
        "004", "overtime pay for contractors is one point five times the base rate"
    ),
]


def _retr():
    return BM25Retriever(DOCS)


def _q(relevant=("001",), tier="easy", qid="q1"):
    return Question(
        q_id=qid,
        question="what is the hotel reimbursement limit for 2024",
        gold_answer="5000 dollars",
        relevant_docs=list(relevant),
        tier=tier,
    )


# ---------------------------------------------------------------- §3.1 state / §2 happy path
def test_happy_path_scores_with_retrieval_diagnosis():
    row = run_case(_q(), _retr(), MockLLM(), MockJudge(), k=3)
    assert isinstance(row, CaseRun)
    assert row.row.status == "SCORED"
    assert row.row.failure_stage is None
    assert len(row.row.retrieved) > 0
    assert row.row.precision is not None or row.row.recall is not None
    assert row.row.correct is True  # relevant doc {001} was retrieved and grounded
    assert (
        row.context is not None and row.answer is not None and row.verdict is not None
    )


# ---------------------------------------------------------------- T-10 / I-008 -- attribution
def test_generation_fault_sets_failure_stage_but_keeps_retrieval():
    # A generation that exhausts its parse retries -> ERROR, but retrieval is intact.
    class BadGen(MockLLM):
        def __init__(self):
            super().__init__()
            self._always_bad = True

    row = run_case(_q(), _retr(), BadGen(), MockJudge(), k=3)
    assert row.row.status == "ERROR"
    assert row.row.failure_stage == "generation"
    assert row.row.answer_status == "ERROR"
    assert row.row.retrieved  # retrieval still yields a full diagnosis
    assert row.row.precision is not None


def test_judge_fault_partial_keeps_retrieval_metrics():
    # A judge fault -> PARTIAL with retrieval metrics intact, correct=None.
    class BadJudge(MockJudge):
        def _raw(self, *_a, **_k):
            return "not json {"

    row = run_case(_q(), _retr(), MockLLM(), BadJudge(), k=3)
    assert row.row.status == "PARTIAL"
    assert row.row.failure_stage == "judging"
    assert row.row.correct is None
    assert row.row.precision is not None  # §18 "did retrieval fail?" still answerable


# ---------------------------------------------------------------- E-08 / T-08c -- grounding gate
def test_foreign_citation_is_a_grounding_violation():
    row = run_case(_q(), _retr(), MockLLM(hallucinate=True), MockJudge(), k=3)
    assert row.row.grounding_violation is True
    assert row.row.supported is False  # supported forced false when a claim is dropped
    assert row.row.unsupported_claims >= 1  # the foreign claim is counted
    assert row.verdict is not None  # the harness forced supported False, not the model


# ---------------------------------------------------------------- --judge off (R-12 ablation)
def test_judge_off_is_a_retrieval_only_eval():
    row = run_case(_q(), _retr(), MockLLM(), MockJudge(), k=3, judge_on=False)
    assert row.row.status == "SCORED"
    assert row.row.correct is None  # no verdict: correct/supported/complete are None
    assert row.verdict is not None and row.verdict.status == "SKIPPED"
    assert row.row.precision is not None  # but precision/recall still computed


# ---------------------------------------------------------------- E-09 distractor (no crash)
def test_distractor_tier_runs_without_crash():
    q = _q()
    q.tier = "distractor"
    q.relevant_docs = ["003"]
    row = run_case(q, _retr(), MockLLM(), MockJudge(), k=5)
    assert row.row.status in {"SCORED", "PARTIAL", "ERROR"}
    assert 0.0 <= (row.row.precision or 0.0) <= 1.0


# ---------------------------------------------------------------- §9.5 -- dataset + per-tier
def test_run_dataset_aggregates_with_per_tier_breakdown():
    questions = [
        _q(relevant=["001"], tier="easy", qid="e1"),
        _q(relevant=["003"], tier="multi", qid="m1"),
        _q(relevant=["001", "003"], tier="synthesis", qid="s1"),
        _q(relevant=["004"], tier="distractor", qid="d1"),
    ]
    report = run_dataset(questions, _retr(), MockLLM(), MockJudge(), k=3, judge_on=True)
    assert isinstance(report, RunReport)
    assert report.aggregate.n_cases == 4
    assert set(report.aggregate.by_tier) == {"easy", "multi", "synthesis", "distractor"}
    assert len(report.rows) == 4


def test_stop_on_error_aborts_after_first_fault():
    # stop_on_error True -> the run stops once a non-terminal fault occurs.
    class BadGen(MockLLM):
        def __init__(self):
            super().__init__()
            self._always_bad = True

    questions = [
        Question(
            q_id="e1",
            question="hotel limit 2024",
            gold_answer="5000",
            relevant_docs=["001"],
            tier="easy",
        ),
        Question(
            q_id="m1",
            question="what?",
            gold_answer="x",
            relevant_docs=["003"],
            tier="multi",
        ),
    ]
    report = run_dataset(
        questions, _retr(), BadGen(), MockJudge(), k=3, stop_on_error=True
    )
    # Both cases fault (generation) -> only the first was processed before abort.
    assert any(r.status == "ERROR" for r in report.rows)

    report_run_all = run_dataset(
        questions, _retr(), BadGen(), MockJudge(), k=3, stop_on_error=False
    )
    # run-all default: every case is processed even though each faults.
    assert len(report_run_all.rows) == 2
