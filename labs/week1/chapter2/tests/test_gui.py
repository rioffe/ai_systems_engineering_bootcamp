"""T-16 -- GUI offscreen cancel semantics (I-014, E-08/E-14/E-16), SPEC ch2 §5.2.

Drives the optional PyQt5 one-question panel *offscreen* (``QT_QPA_PLATFORM=offscreen``,
set by ``conftest``), with **no Ollama** (I-011) and **no display** -- the exact three
clauses T-16 pins:

* **E-16**  starting a run while one is active yields *exactly one* live worker: the
   UI guards the button, and the Cancel/respawn path tears the prior worker down so a
   superseded worker's *late* signals cannot clobber the run in flight.
* **I-014** after ``Cancel`` **zero workers are alive** -- no live worker survives a
   teardown.
* **E-14/E-08** the cancelled case settles to a **terminal ``ERROR`` panel naming
   ``failure_stage="generation"``** (the stage the run was in when it was cancelled).

The generation step is blocked behind a release gate so the test can observe the worker
*mid-generation* and cancel it deterministically: ``run_case``'s cooperative cancel token
(``cancel_check``) is only consulted at the checkpoint that *follows* a stage, so a real
"slow" generation must finish before the Cancel lands -- which is why a mid-generation
cancel surfaces at the ``generation`` stage.
"""

# T-16 is a GUI test: it self-skips cleanly when the optional `gui` extra (PyQt5) is
# absent, so `uv run pytest` (T-14) stays green on a headless, no-Qt install.
import pytest

pytest.importorskip("PyQt5", reason="optional `gui` extra (PyQt5) not installed")
pytest.importorskip("PyQt5.QtWidgets")
pytest.importorskip("PyQt5.QtCore")

import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QEventLoop, QTimer  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from rag_eval.judgment import MockJudge  # noqa: E402
from rag_eval.model import MockLLM  # noqa: E402
from rag_eval.retrieval import BM25Retriever  # noqa: E402
from rag_eval.types import Document, Question  # noqa: E402
from rag_eval.ui import CaseWorker, MainWindow  # noqa: E402

# A bounded wait so a forgotten release / a wedged worker can never hang the suite.
_WAIT = 5.0

# A tiny grounded corpus + question (mirrors test_pipeline's). BM25 over these returns a
# ranked list, so the pipeline reaches the (probabilistic) generation stage where the
# cancel is exercised; the quality of the verdict is irrelevant -- we only care that the
# run is torn down cleanly and attributed to the correct stage.
DOCS = [
    Document(
        "001",
        "the reimbursement limit for hotels is five thousand dollars effective 2024",
    ),
    Document("002", "visa applications require two photos and a ten dollar fee"),
    Document("003", "the hotel per-diem cap for new hires is one thousand dollars"),
    Document(
        "004", "overtime pay for contractors is one point five times the base rate"
    ),
]
QUESTION = Question(
    q_id="g1",
    question="what is the hotel reimbursement limit for 2024",
    gold_answer="5000 dollars",
    relevant_docs=["001"],
    tier="easy",
)


class _BlockingLLM(MockLLM):
    """A generation double that blocks until its release event fires -- a "slow" model.

    ``_raw`` is the hook the ``generate`` retry loop calls for each attempt, so blocking
    there parks the worker *in* the generation stage. The bounded ``release.wait`` cap
    guarantees the thread always finishes even if a release is forgotten, so no test can
    hang the session.
    """

    def __init__(
        self, release: threading.Event, entered: threading.Event | None = None
    ):
        super().__init__()
        self._release = release
        self._entered = entered

    def _raw(self, *args, **kwargs) -> str:
        if self._entered is not None:
            self._entered.set()  # signal: the worker is now mid-generation
        self._release.wait(_WAIT)
        return super()._raw(*args, **kwargs)  # a schema-valid grounded answer


@pytest.fixture(scope="session")
def qapp():
    """A single offscreen QApplication for the whole suite (created before any window)."""
    app = QApplication.instance() or QApplication([])
    yield app


def _window(qapp, blocking: _BlockingLLM) -> MainWindow:
    """A grounded panel wired to a blocking backend (injected => no Ollama, I-011)."""
    win = MainWindow(
        llm=blocking,
        judge=MockJudge(),
        retriever=BM25Retriever(DOCS),
        questions=[QUESTION],
    )
    win.question_edit.setPlainText(QUESTION.question)
    return win


def _start_and_enter(
    win: MainWindow, release: threading.Event, entered: threading.Event
):
    """Start a run and block until its worker is observed mid-generation."""
    win.on_run()
    assert win.current_state() == "RUNNING"
    assert entered.wait(_WAIT), "worker did not reach the generation stage"
    worker = win._worker  # the tracked worker; capture the reference for teardown
    assert worker is not None and worker.isRunning()
    assert len(win.live_workers()) == 1
    return worker


def _cancel_and_settle(win: MainWindow, release: threading.Event, worker: CaseWorker):
    """Cancel the live worker, release the (cooperative) gate, and settle via the loop.

    Spins the main-thread event loop so the worker's *queued* ``result_ready`` /
    ``finished`` cross-thread signals are delivered -- which runs ``_settle`` (nilling
    the tracked worker, clearing the ``active`` flag, and emitting ``run_settled``).
    """
    win.on_cancel()  # the user's Cancel button -> the cooperative teardown
    release.set()  # let the gated generation return so the checkpoint lands the cancel
    loop = QEventLoop()
    settled = {"v": False}

    def _done() -> None:
        settled["v"] = True
        loop.quit()

    win.run_settled.connect(_done)
    QTimer.singleShot(int(_WAIT * 1000), loop.quit)
    try:
        loop.exec_()
    finally:
        win.run_settled.disconnect(_done)
    worker.wait(int(_WAIT * 1000))  # join so no live QThread lingers past the run
    assert settled["v"], "run did not settle within the timeout"
    # A settled window is idle with no live worker (I-014).
    assert win.current_state() == "IDLE"
    assert win.live_workers() == []


# ---------------------------------------------------------------- T-16 -- offscreen launch
def test_offscreen_window_launches(qapp):
    """The panel builds and is idle with zero live workers -- no Ollama, no display."""
    win = _window(qapp, _BlockingLLM(threading.Event(), threading.Event()))
    try:
        assert win.current_state() == "IDLE"
        assert win.live_workers() == []
        # The injected offline double is advertised on the banner (E-11 fallback / I-011).
        assert "injected" in win.lbl_banner.text().lower()
    finally:
        win.close()


# ---------------------------------------------------------------- T-16 / E-16 -- single pipeline
def test_run_while_active_keeps_a_single_pipeline(qapp):
    """Starting a run while one is active yields exactly one live worker (E-16/I-014)."""
    release = threading.Event()
    entered = threading.Event()
    win = _window(qapp, _BlockingLLM(release, entered))
    worker = None
    try:
        worker = _start_and_enter(win, release, entered)
        assert (
            not win.btn_run.isEnabled()
        )  # gated: the button is disabled while running

        # A second Run while active is a *no-op*: the prior worker is neither replaced nor
        # cancelled spuriously -- there is exactly one pipeline at a time.
        win.on_run()
        assert win._worker is worker
        assert len(win.live_workers()) == 1
        assert not worker.is_cancelled
        assert not win.btn_run.isEnabled()

        # Teardown: Cancel tears the single worker down cleanly.
        _cancel_and_settle(win, release, worker)
    finally:
        if worker is not None:
            worker.wait(int(_WAIT * 1000))
        win.close()


# ---------------------------------------------------------------- T-16 / I-014 + E-14/E-08 -- cancel
def test_cancel_leaves_no_worker_and_terminal_generation_error(qapp):
    """After Cancel: zero live workers, and the panel is a terminal ERROR at generation
    (I-014 + E-14/E-08)."""
    release = threading.Event()
    entered = threading.Event()
    win = _window(qapp, _BlockingLLM(release, entered))
    worker = None
    try:
        worker = _start_and_enter(win, release, entered)

        # E-14: a mid-generation cancel is surfaced through the Cancel button. The
        # teardown clears the ``active`` flag immediately so the UI repaints to IDLE.
        win.on_cancel()
        assert worker.is_cancelled
        assert win.current_state() == "IDLE"

        _cancel_and_settle(win, release, worker)

        # I-014: no live worker survives a Cancel.
        assert win.live_workers() == []

        # E-14/E-08: the case settled to a terminal ERROR attributed to the stage it was
        # cancelled in -- generation, with the full retrieval diagnosis intact (I-008).
        case = win.last_case
        assert case is not None
        assert case.row.status == "ERROR"
        assert (
            case.row.failure_stage == "generation"
        )  # E-14: the stage it was cancelled in
        assert case.row.retrieved  # retrieval is still diagnosable

        # ... and the panel actually renders it.
        assert win.lbl_status.text() == "ERROR"
        assert "failure_stage=generation" in win.lbl_error.text()
    finally:
        if worker is not None:
            worker.wait(int(_WAIT * 1000))
        win.close()


# ---------------------------------------------------------------- T-16 / E-16 -- respawn supersedes
def test_respawn_supersedes_the_prior_worker(qapp):
    """A fresh run supersedes a cancelled one: the new worker is the sole live pipeline
    and the superseded worker's case cannot clobber it (E-16 / the clobber guard)."""
    win = MainWindow(
        llm=_BlockingLLM(threading.Event(), threading.Event()),
        judge=MockJudge(),
        retriever=BM25Retriever(DOCS),
        questions=[QUESTION],
    )
    win.question_edit.setPlainText(QUESTION.question)

    # --- Phase A: one run in flight, then cancelled to a terminal generation ERROR. ---
    release_a = threading.Event()
    entered_a = threading.Event()
    blocking_a = _BlockingLLM(release_a, entered_a)
    win._llm = blocking_a
    worker_a = None
    try:
        worker_a = _start_and_enter(win, release_a, entered_a)
        _cancel_and_settle(win, release_a, worker_a)
        case_a = win.last_case
        assert case_a is not None and case_a.row.failure_stage == "generation"

        # --- Phase B: a new run. It must become the single live worker; the settled
        # predecessor is gone and its late signals are ignored, so it can't clobber B. ---
        release_b = threading.Event()
        entered_b = threading.Event()
        blocking_b = _BlockingLLM(release_b, entered_b)
        win._llm = blocking_b
        worker_b = _start_and_enter(win, release_b, entered_b)

        assert win._worker is worker_b
        assert worker_b is not worker_a
        assert (
            len(win.live_workers()) == 1
        )  # exactly one -- A is no longer tracked/live
        assert case_a is win.last_case  # B hasn't settled yet, so it hasn't clobbered A
    finally:
        if worker_b is not None:
            win.on_cancel()
            release_b.set()
            _settle_only(win, worker_b, release_b)
        if worker_a is not None:
            worker_a.wait(int(_WAIT * 1000))
        win.close()


def _settle_only(win: MainWindow, worker: CaseWorker, release: threading.Event) -> None:
    """Teardown for the respawn phase: let B settle without the idle-panel assertions."""
    loop = QEventLoop()

    def _done() -> None:
        loop.quit()

    win.run_settled.connect(_done)
    QTimer.singleShot(int(_WAIT * 1000), loop.quit)
    try:
        loop.exec_()
    finally:
        win.run_settled.disconnect(_done)
    worker.wait(int(_WAIT * 1000))
    assert win.live_workers() == []
