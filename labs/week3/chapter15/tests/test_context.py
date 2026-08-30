"""R-03 / R-10 / K-05 / K-09 / I-005 / I-007: deterministic context engineering.

`C_t` is composed deterministically from the task, a SELECTED working set (never
the whole repo, I-005), and recent feedback (verifier output, I-007). The budget
is measured in characters (K-09, default 8000); overflow triggers compaction
(R-10/K-05) -- preserving salient state and discarding redundant history -- or,
under `--no-compact`, a BudgetOverflow the loop maps to STALLED:BUDGET (E-13).
"""

from coding_agent.context import (
    DEFAULT_BUDGET,
    BudgetOverflow,
    Context,
    ContextManager,
)
from coding_agent.task import Task
from coding_agent.verifier import VerifySpec


def _task(prompt="fix the parser"):
    return Task(
        task_id="parse-config",
        prompt=prompt,
        target_repo="/repo",
        verifier=VerifySpec(kind="tests", command="pytest -q"),
    )


# ---------------------------------------------------------------- R-03 / I-005
def test_compose_is_deterministic():
    def build():
        cm = ContextManager(budget=1000)
        cm.add_file("a.py", "A = 1")
        cm.add_feedback("test failed: expected 1 got 2")
        return cm.compose(_task(), iteration=2).text

    assert build() == build()


def test_compose_contains_task_and_working_set():
    cm = ContextManager(budget=1000)
    cm.add_file("repo/config.py", "X = 1")
    text = cm.compose(_task(prompt="parse the config file"), iteration=1).text
    assert "parse the config file" in text
    assert "repo/config.py" in text
    assert "X = 1" in text


def test_context_is_selected_not_bulk():
    # I-005: only explicitly selected files reach the policy, never the whole repo.
    cm = ContextManager(budget=1000)
    cm.add_file("keep.py", "keep")
    text = cm.compose(_task(), iteration=1).text
    assert "unselected_file.py" not in text
    assert "keep.py" in text


def test_verifier_feedback_reaches_next_context():
    # I-007: verifier output is a reasoning signal in the next C_t.
    cm = ContextManager(budget=1000)
    cm.add_file("a.py", "A = 1")
    cm.add_feedback("FAILED: assert 1 == 2 at test_config.py:7")
    text = cm.compose(_task(), iteration=2).text
    assert "FAILED: assert 1 == 2 at test_config.py:7" in text


# ---------------------------------------------------------------- K-09 budget
def test_default_budget_is_8000_chars():
    # K-09: the compact trigger is measured in characters, BUDGET default 8000.
    assert DEFAULT_BUDGET == 8000
    assert ContextManager().budget == 8000


def test_context_reports_char_size():
    # K-07/K-09 unit consistency: chars is the unit everywhere.
    cm = ContextManager(budget=1000)
    cm.add_file("a.py", "A = 1")
    ctx = cm.compose(_task(), iteration=1)
    assert isinstance(ctx, Context)
    assert ctx.chars == len(ctx.text)
    assert ctx.compacted is False
    assert ctx.budget == 1000


# ---------------------------------------------------------------- R-10 / K-05 compaction
def test_compaction_fires_on_overflow():
    # K-05/K-09: |C_t| > BUDGET -> compaction fires (not a pass-through).
    big = "x" * 900
    cm = ContextManager(budget=1000)
    for i in range(5):
        cm.add_file(f"f{i}.py", big)
    cm.add_feedback("old noise one")
    cm.add_feedback("old noise two")
    cm.add_feedback("last verdict FAILED: 1 of 2 tests")
    ctx = cm.compose(_task(), iteration=5)
    assert ctx.compacted is True
    assert ctx.budget == 1000
    assert ctx.chars == len(ctx.text)


def test_compaction_preserves_salient_state():
    # R-10: compaction preserves the task, open files (latest), last verdict.
    cm = ContextManager(budget=500)
    cm.add_file("a.py", "OLD CONTENT")
    cm.add_file("a.py", "NEW CONTENT")  # open edit: latest version wins
    cm.add_feedback("first feedback")
    cm.add_feedback("last verdict FAILED: 1 of 2 tests")
    cm.add_feedback("x" * 500)  # pushes over budget
    ctx = cm.compose(_task(prompt="fix parser bug"), iteration=3)
    assert ctx.compacted is True
    assert "fix parser bug" in ctx.text
    assert "NEW CONTENT" in ctx.text
    assert "OLD CONTENT" not in ctx.text  # redundant history discarded
    assert "last verdict FAILED: 1 of 2 tests" in ctx.text
    assert "first feedback" not in ctx.text  # older feedback discarded


def test_no_compact_overflow_raises():
    # E-13: --no-compact (compact=False) overflow -> BudgetOverflow -> STALLED:BUDGET.
    cm = ContextManager(budget=100, compact=False)
    cm.add_file("big.py", "x" * 500)
    try:
        cm.compose(_task(), iteration=1)
        assert False, "expected BudgetOverflow"
    except BudgetOverflow:
        pass


def test_under_budget_never_compacts():
    cm = ContextManager(budget=100000)
    cm.add_file("a.py", "A = 1")
    assert cm.compose(_task(), iteration=1).compacted is False
