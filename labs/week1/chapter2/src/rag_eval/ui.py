r"""R-13 / SPEC section 5.2 -- the optional PyQt5 GUI surface (`rag-gui`).

A one-question-at-a-time view over the *same* pipeline modules the CLI uses
(retrieval, context, model, judgment, metrics -- R-13): the operator types a question
(or loads one from the grounded dataset), clicks Run, and watches the ranked BM25
retrieval (with scores and a truncation badge), the grounded answer with its cited
sources, and the LLM-as-judge verdict ({correct, supported, complete}) plus the per-case
metrics, all on the right. The pipeline runs off the Qt event-loop thread in a
CaseWorker (ch1 section 3.3 pattern; I-014); the UI only ever reacts to *queued* signals,
so it stays responsive and a Cancel tears the worker down to a terminal ERROR panel
naming ``failure_stage="generation"`` (E-14) without leaving a live worker behind
(E-16 / T-16).

Backend discovery mirrors the CLI (E-11/E-12): on start it probes Ollama and, when the
daemon is unreachable, degrades to the offline ``MockLLM`` / ``MockJudge`` and says so on
the banner -- never requiring a network to *import* or *launch*. The window is fully
injectable (``llm`` / ``judge`` / ``retriever`` / ``questions``) so the offscreen T-16
test drives a blocking double and asserts the cancel semantics with no Qt display and no
Ollama.
"""

from __future__ import annotations

import threading

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .judgment import Judge, MockJudge, OllamaJudge
from .metrics import retrieval_pr
from .model import (
    LLM,
    MockLLM,
    ModelNotFoundError,
    OllamaClient,
    OllamaError,
    OllamaLLM,
)
from .pipeline import CaseRun, run_case
from .retrieval import BM25Retriever
from .types import Context, Question, RunMetrics

# The "mock" sentinel used throughout the model combo.
MOCK = "mock"
# K-03 defaults, surfaced as the control starting values.
DEFAULT_K = 5
DEFAULT_BUDGET = 2000
DEFAULT_MAX_RETRIES = 2
DEFAULT_MAX_TOKENS = 512
DEFAULT_MODEL = "qwen3.8:27b-mlx"

# Shared pill/pad styling for the status + verdict labels.
PILL_BASE = (
    "font-weight: bold; padding: 1px 6px; border: 1px solid; border-radius: 3px; "
)


# ---------------------------------------------------------------------- the worker


class CaseWorker(QThread):
    """Run ONE question through the pipeline off the UI thread (ch1 section 3.3 / I-014).

     It reuses ``run_case`` verbatim, threading a cooperative cancel token (``cancel`` ->
    the worker's ``threading.Event``) through ``run_case``'s ``cancel_check`` so a Cancel
    settles the case as a terminal ERROR at the stage it was in (E-14). Exactly one
     *terminal* ``result_ready`` always fires (even on an uncaught crash, where a fallback
    terminal CaseRun is built), so the UI settles and no live worker survives a cancel
     (I-014 / T-16).
    """

    #: The finished per-case result (always a terminal CaseRun, on every path).
    result_ready = pyqtSignal(object)
    #: An uncaught fault surfaced on the panel's error line (informational; result_ready
    #: still settles the run).
    crashed = pyqtSignal(str)

    def __init__(
        self,
        retriever: BM25Retriever,
        llm: LLM,
        judge: Judge,
        *,
        question: Question,
        k: int = DEFAULT_K,
        token_budget: int = DEFAULT_BUDGET,
        judge_on: bool = True,
        seed: int = 42,
        max_retries: int = DEFAULT_MAX_RETRIES,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        super().__init__()
        self._retriever = retriever
        self._llm = llm
        self._judge = judge
        self._question = question
        self._k = k
        self._token_budget = token_budget
        self._judge_on = judge_on
        self._seed = seed
        self._max_retries = max_retries
        self._max_tokens = max_tokens
        self._cancel = threading.Event()
        self._thread_id: int | None = None

    # -- main-thread, thread-safe cancel control (E-14 / E-16) --

    def cancel(self) -> None:
        """Teardown request: the next inter-stage checkpoint settles the case as ERROR."""
        self._cancel.set()

    @property
    def is_cancelled(self) -> bool:
        return self._cancel.is_set()

    @property
    def thread_id(self) -> int | None:
        return self._thread_id

    # -- worker thread --

    def run(self) -> None:
        self._thread_id = threading.get_ident()
        case: CaseRun | None
        try:
            case = run_case(
                self._question,
                self._retriever,
                self._llm,
                self._judge,
                k=self._k,
                token_budget=self._token_budget,
                judge_on=self._judge_on,
                seed=self._seed,
                max_retries=self._max_retries,
                max_tokens=self._max_tokens,
                cancel_check=self._cancel.is_set,
            )
        except (OllamaError, ModelNotFoundError) as exc:
            # E-11/E-12: a fatal backend fault surfaces as a terminal generation-stage
            # ERROR so the panel settles and no worker lingers (I-014).
            self.crashed.emit(str(exc))
            case = _terminal_generation_error(self._question, self._retriever, str(exc))
        except Exception as exc:
            # E-07 analog: any uncaught fault still settles the panel terminally.
            self.crashed.emit(f"{type(exc).__name__}: {exc}")
            case = _terminal_generation_error(
                self._question, self._retriever, f"crashed: {type(exc).__name__}: {exc}"
            )
        # Exactly one terminal result on every path: the UI settles and a cancel leaves
        # no live worker (I-014 / T-16).
        assert case is not None
        self.result_ready.emit(case)


def _terminal_generation_error(
    question: Question, retriever: BM25Retriever, error: str
) -> CaseRun:
    """A fallback terminal CaseRun for a crashed/fatal run (E-14 / I-008).

    Keeps the retrieval fields so the diagnosis is complete and names the stage
     "generation" -- the most likely probabilistic fault for a crashed/fatal run.
    """
    row = RunMetrics(
        q_id=question.q_id,
        tier=question.tier,
        expected=list(question.relevant_docs),
    )
    scored: list = []
    try:
        scored = retriever.search(question.question, DEFAULT_K)
        row.retrieved = [sd.doc.doc_id for sd in scored]
        tp, fp, fn, p, r, f1 = retrieval_pr(question.relevant_docs, row.retrieved)
        row.tp, row.fp, row.fn = tp, fp, fn
        row.precision, row.recall, row.f1 = p, r, f1
    except Exception:
        scored = []
    row.failure_stage = "generation"
    row.status = "ERROR"
    row.answer_status = "ERROR"
    empty = Context(docs=[], prompt="", provenance=[], tokens=0, truncated=False)
    return CaseRun(
        row=row,
        question=question,
        retrieved=scored,
        context=empty,
        answer=None,
        verdict=None,
    )


# ---------------------------------------------------------------------- the window


class MainWindow(QMainWindow):
    """The section 5.2 one-question eval panel.

    Built with injected dependencies (``retriever`` / ``llm`` / ``judge`` / ``questions``)
    so the offscreen T-16 test needs neither Ollama nor a display; when un-injected it
    discovers a backend the ch1 way and degrades to the offline mocks with a banner.
    """

    run_settled = pyqtSignal()

    def __init__(
        self,
        app: object | None = None,
        *,
        llm: LLM | None = None,
        judge: Judge | None = None,
        retriever: BM25Retriever | None = None,
        questions: list[Question] | None = None,
        ollama_host: str | None = None,
        model: str | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("RAG Eval -- context IS the program (ch2, section 1)")

        self._questions = list(questions) if questions is not None else []
        self._retriever = retriever
        self._llm = llm
        self._judge = judge
        self._ollama_host = ollama_host
        self._model = model or DEFAULT_MODEL
        self._grounded_q: Question | None = None
        self._loading = False
        self._worker: CaseWorker | None = None
        self._active = False
        self._last: CaseRun | None = None
        self._used_fallback = False
        self._client: OllamaClient | None = None
        self._question: Question | None = None

        self._build_ui()
        self._refresh_backend()

    # --------------------------------------------------------- construction

    def _build_ui(self) -> None:
        self._build_controls()
        self._build_results()
        outer = QHBoxLayout()
        outer.addWidget(self._left_box, 0)
        outer.addWidget(self._right_box, 1)
        central = QWidget()
        central.setLayout(outer)
        self.setCentralWidget(central)
        self.resize(1280, 800)

    def _build_controls(self) -> QWidget:
        self._left_box = QGroupBox("Question & Parameters")
        box = QVBoxLayout(self._left_box)

        self.lbl_banner = QLabel("")
        box.addWidget(self.lbl_banner)

        box.addWidget(QLabel("Question (type one, or load a grounded question below)"))
        self.question_edit = QPlainTextEdit()
        self.question_edit.setPlaceholderText("Enter a question (required).")
        self.question_edit.textChanged.connect(self._on_question_edited)
        box.addWidget(self.question_edit, 1)

        self._question_combo = None
        if self._questions:
            box.addWidget(
                QLabel("Grounded question (from dataset; gives a ground truth)")
            )
            combo = QComboBox()
            combo.addItems(f"{q.q_id}: {q.question[:48]}" for q in self._questions)
            combo.currentIndexChanged.connect(self._on_question_selected_index)
            box.addWidget(combo)
            self._question_combo = combo

        grid = QGridLayout()
        self._model_combo = QComboBox()
        self.spin_k = QSpinBox()
        self.spin_k.setRange(1, 100)
        self.spin_k.setValue(DEFAULT_K)
        self.spin_budget = QSpinBox()
        self.spin_budget.setRange(1, 1_000_000)
        self.spin_budget.setValue(DEFAULT_BUDGET)
        self.spin_budget.valueChanged.connect(self._validate)
        self.chk_judge = QCheckBox("Run LLM-as-judge")
        self.chk_judge.setChecked(True)
        self.chk_judge.stateChanged.connect(self._validate)
        rows = [
            ("Model", self._model_combo),
            ("top-k", self.spin_k),
            ("token budget", self.spin_budget),
            ("Judge", self.chk_judge),
        ]
        for row_idx, (label, widget) in enumerate(rows):
            grid.addWidget(QLabel(label), row_idx, 0)
            grid.addWidget(widget, row_idx, 1)
        box.addLayout(grid)

        buttons = QHBoxLayout()
        self.btn_run = QPushButton("Run")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_run.clicked.connect(self.on_run)
        self.btn_cancel.clicked.connect(self.on_cancel)
        buttons.addWidget(self.btn_run)
        buttons.addWidget(self.btn_cancel)
        buttons.addStretch(1)
        box.addLayout(buttons)

        self.lbl_message = QLabel("")
        self.lbl_message.setStyleSheet("color: #c62828;")
        box.addWidget(self.lbl_message)
        self.lbl_state = QLabel("state: IDLE")
        box.addWidget(self.lbl_state)
        return self._left_box

    def _build_results(self) -> QWidget:
        self._right_box = QGroupBox("Retrieval · Answer · Verdict")
        layout = QVBoxLayout(self._right_box)

        self._case = QGroupBox("Per-case")
        case_grid = QGridLayout(self._case)
        self.lbl_qid = QLabel("--")
        self.lbl_qid.setStyleSheet("font-weight: bold;")
        self.lbl_tier = QLabel("--")
        self.lbl_status = QLabel("--")
        case_grid.addWidget(self.lbl_qid, 0, 0)
        case_grid.addWidget(self.lbl_tier, 0, 1)
        case_grid.addWidget(self.lbl_status, 0, 2)
        self.lbl_metric = QLabel("p= --  r= --  f1= --  tokens= --   lat= -- ms")
        case_grid.addWidget(self.lbl_metric, 1, 0, 1, 3)
        self.lbl_cost = QLabel("latency: --")
        case_grid.addWidget(self.lbl_cost, 2, 0, 1, 3)
        layout.addWidget(self._case)

        self._retrieve = QGroupBox("Retrieval (ranked by BM25)")
        ret_layout = QVBoxLayout(self._retrieve)
        self.trunc_badge = QLabel("")
        self.trunc_badge.setStyleSheet("color: #b26a00; font-weight: bold;")
        self.trunc_badge.setVisible(False)
        self.tbl_retrieval = QTableWidget(0, 4)
        self.tbl_retrieval.setHorizontalHeaderLabels(
            ["rank", "doc_id", "score", "in ctx"]
        )
        self.tbl_retrieval.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_retrieval.setEditTriggers(QTableWidget.NoEditTriggers)
        ret_layout.addWidget(self.trunc_badge)
        ret_layout.addWidget(self.tbl_retrieval, 1)
        self.budget_bar = QProgressBar()
        self.budget_bar.setRange(0, DEFAULT_BUDGET)
        self.budget_bar.setValue(0)
        self.budget_bar.setFormat("%v / %m tokens")
        ret_layout.addWidget(self.budget_bar)
        layout.addWidget(self._retrieve, 1)

        self._result = QGroupBox("Answer + Verdict")
        res_layout = QGridLayout(self._result)
        self.answer_edit = QPlainTextEdit()
        self.answer_edit.setReadOnly(True)
        self.answer_edit.setPlaceholderText("(grounded answer appears here)")
        res_layout.addWidget(self.answer_edit, 0, 0, 7, 1)
        self.lbl_confidence = QLabel("confidence: --")
        res_layout.addWidget(self.lbl_confidence, 0, 1)
        self.lbl_sources = QLabel("sources: --")
        res_layout.addWidget(self.lbl_sources, 1, 1)
        self.lbl_correct = QLabel("correct: --")
        self.lbl_supported = QLabel("supported: --")
        self.lbl_complete = QLabel("complete: --")
        res_layout.addWidget(self.lbl_correct, 2, 1)
        res_layout.addWidget(self.lbl_supported, 3, 1)
        res_layout.addWidget(self.lbl_complete, 4, 1)
        self.lbl_halluc = QLabel("hallucination: --")
        res_layout.addWidget(self.lbl_halluc, 5, 1)
        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet("color: #c62828;")
        res_layout.addWidget(self.lbl_error, 6, 1)
        layout.addWidget(self._result, 1)
        return self._right_box

    # --------------------------------------------------------- validation (section 5.2)

    def _validate(self, *args: object) -> bool:
        # Controls validated ch1 section 5.2 style: k in [1,100] and budget >= 1 are
        # enforced by the spin ranges; only gate the Run button on a non-empty question
        # while idle.
        ok = True
        message = ""
        if not self._question_edit_nonempty():
            ok = False
            message = "Question must not be empty"
        self.lbl_message.setText(message)
        if not self._active:
            self.btn_run.setEnabled(ok)
        return ok

    # --------------------------------------------------------- question selection

    def _on_question_selected_index(self, index: int) -> None:
        if index < 0 or index >= len(self._questions):
            return
        q = self._questions[index]
        self._grounded_q = q
        self._load_question_text(q.question)

    def _on_question_edited(self) -> None:
        # A genuine edit makes the run free-text: drop the ground-truth association.
        if not self._loading:
            self._grounded_q = None

    def _load_question_text(self, text: str) -> None:
        self._loading = True
        self.question_edit.setPlainText(text)
        self._loading = False
        self._validate()

    # --------------------------------------------------------- actions

    def on_run(self) -> None:
        if self._active or not self._validate():
            return
        # E-16: a new Run cancels any prior worker first; exactly one worker at a time.
        self.cancel_run()
        self._active = True
        self._question = self._current_question()
        self._spawn_worker()
        self._update_running()

    def on_cancel(self) -> None:
        self.cancel_run()

    def cancel_run(self) -> None:
        # E-14/E-16: tear the worker down; its cancel token settles it to terminal ERROR.
        self._active = False
        worker = self._worker
        if worker is not None:
            worker.cancel()
        self._update_running()

    def _current_question(self) -> Question:
        # A selected/loaded dataset question keeps its ground truth; otherwise the typed
        # text becomes a synthetic "free" question (no ground truth, relevant_docs=[]).
        text = self.question_edit.toPlainText().strip()
        if self._grounded_q is not None and self._grounded_q.question == text:
            return self._grounded_q
        return Question(q_id="free", question=text, gold_answer="", relevant_docs=[])

    def _spawn_worker(self) -> None:
        llm, judge = self._build_backend()
        # Track the run *before* wiring it, so every handler can tell the run in
        # flight from a superseded predecessor: a cancel+respawn (E-16) must not let
        # an older worker's late signals clobber the new run or stick the flag
        # (I-008/I-014). Each closure captures its own worker by default-arg so the
        # binding is stable across queued cross-thread signal delivery.
        worker = CaseWorker(
            self._retriever,
            llm,
            judge,
            question=self._question,
            k=self.spin_k.value(),
            token_budget=self.spin_budget.value(),
            judge_on=self.chk_judge.isChecked(),
            max_tokens=DEFAULT_MAX_TOKENS,
            max_retries=DEFAULT_MAX_RETRIES,
        )
        self._worker = worker

        def _on_result(case: CaseRun, _w: CaseWorker = worker) -> None:
            if self._worker is _w:
                self._show_result(case)

        def _on_crashed(message: str, _w: CaseWorker = worker) -> None:
            if self._worker is _w:
                self._surface_crash(message)

        def _on_finished(_w: CaseWorker = worker) -> None:
            self._settle(_w)

        worker.result_ready.connect(_on_result)
        worker.crashed.connect(_on_crashed)
        worker.finished.connect(_on_finished)
        self._reset_panel()
        self._update_running()
        worker.start()

    def _build_backend(self) -> tuple[LLM, Judge]:
        if self._llm is not None and self._judge is not None:
            return self._llm, self._judge
        model = self._model_combo.currentText()
        if model == MOCK or self._used_fallback:
            return MockLLM(), MockJudge()
        return OllamaLLM(model, client=self._client), OllamaJudge(
            model, client=self._client
        )

    # --------------------------------------------------------- result handlers

    def _show_result(self, case: CaseRun) -> None:
        self._last = case
        self._show_case(case)

    def _surface_crash(self, message: str) -> None:
        self.lbl_error.setText(message)

    def _settle(self, worker: CaseWorker) -> None:
        # The run's QThread is done. Only a finish for the *tracked* worker settles
        # the window: it drops the reference so no live worker outlives the run
        # (I-014) and clears the active flag -- so a normal *or* cancelled completion
        # always repaints the state panel back to IDLE and re-enables Run. The
        # terminal panel was already rendered by the result_ready handler; a
        # superseded predecessor (self._worker is no longer `worker`) is ignored so it
        # can neither clobber the new run nor clear its state (E-16/I-008).
        if self._worker is not worker:
            return
        self._worker = None
        self._active = False
        self._update_running()
        self.run_settled.emit()

    def _update_running(self) -> None:
        running = self._active
        self.btn_run.setEnabled((not running) and self._question_edit_nonempty())
        self.btn_cancel.setEnabled(running)
        self.lbl_state.setText("state: RUNNING" if running else "state: IDLE")

    def _question_edit_nonempty(self) -> bool:
        return bool(self.question_edit.toPlainText().strip())

    # --------------------------------------------------------- panel rendering

    def _reset_panel(self) -> None:
        row = RunMetrics(q_id="--", tier="--")
        self._render_metrics(row)
        self.tbl_retrieval.setRowCount(0)
        self.trunc_badge.setVisible(False)
        self.budget_bar.setValue(0)
        self.answer_edit.clear()
        self.lbl_confidence.setText("confidence: --")
        self.lbl_sources.setText("sources: --")
        self.lbl_sources.setStyleSheet("")
        for pill in (self.lbl_correct, self.lbl_supported, self.lbl_complete):
            name = pill.text().split(":")[0]
            pill.setText(f"{name}: --")
            pill.setStyleSheet("color: gray;")
        self.lbl_halluc.setText("hallucination: --")
        self.lbl_error.setText("")

    def _show_case(self, case: CaseRun) -> None:
        row = case.row
        self._render_metrics(row)
        self.trunc_badge.setText("")

        # -- retrieval ranking with scores + truncation badge --
        relevant = set(case.question.relevant_docs)
        self._render_retrieval(case.retrieved, relevant)
        context = case.context
        if context is not None and context.truncated:
            self.trunc_badge.setText("TRUNCATED (docs dropped to fit token budget)")
            self.trunc_badge.setVisible(True)
        else:
            self.trunc_badge.setVisible(False)
        tokens = context.tokens if context is not None else row.context_tokens
        self._set_budget_bar(tokens)

        # -- answer + sources --
        answer = case.answer
        if answer is not None:
            self.answer_edit.setPlainText(answer.text or "(empty answer)")
            self.lbl_confidence.setText(f"confidence: {answer.confidence:.2f}")
            self.lbl_sources.setText(
                f"sources: {', '.join(answer.sources) or '(none)'}"
            )
            if row.grounding_violation:
                self.lbl_sources.setStyleSheet("color: #b26a00;")
            else:
                self.lbl_sources.setStyleSheet("")
        else:
            self.answer_edit.setPlainText("(no answer -- generation did not complete)")
            self.lbl_confidence.setText("confidence: --")
            self.lbl_sources.setText("sources: --")

        # -- verdict pills + per-case metrics --
        verdict = case.verdict
        self._render_pill(
            self.lbl_correct, "correct", verdict.correct if verdict else None
        )
        self._render_pill(
            self.lbl_supported, "supported", verdict.supported if verdict else None
        )
        self._render_pill(
            self.lbl_complete, "complete", verdict.complete if verdict else None
        )
        self.lbl_halluc.setText(
            _halluc_text(row.unsupported_claims, row.total_factual_claims)
        )

        self.lbl_status.setText(row.status)
        self.lbl_status.setStyleSheet(_pill_color(row.status))
        if row.failure_stage:
            self.lbl_error.setText(f"failure_stage={row.failure_stage}")
        else:
            self.lbl_error.setText("")

    def _render_retrieval(self, scored: list, relevant: set[str]) -> None:
        self.tbl_retrieval.setRowCount(len(scored))
        for i, sd in enumerate(scored):
            mark = "*" if sd.doc.doc_id in relevant else " "
            self.tbl_retrieval.setItem(i, 0, QTableWidgetItem(str(sd.rank)))
            self.tbl_retrieval.setItem(i, 1, QTableWidgetItem(sd.doc.doc_id))
            self.tbl_retrieval.setItem(i, 2, QTableWidgetItem(f"{sd.score:.3f}"))
            self.tbl_retrieval.setItem(i, 3, QTableWidgetItem(mark))

    def _render_metrics(self, row: RunMetrics) -> None:
        self.lbl_qid.setText(row.q_id)
        self.lbl_tier.setText(f"[{row.tier}]")
        # A free-text question carries no ground truth (relevant_docs=[]), so retrieval
        # P/R/F1 are not evaluable. Show them as n/a, not a misleading "0.000" that
        # reads like a zero-recall retrieval *failure* sitting next to a clean verdict
        # (the math already yields P=0, R=None, F1=0 for an empty expected set -- I-007
        # guards the division, but the value is meaningless without a ground truth).
        if row.expected:
            p = " --" if row.precision is None else f"{row.precision:.3f}"
            r = " --" if row.recall is None else f"{row.recall:.3f}"
            f1 = " --" if row.f1 is None else f"{row.f1:.3f}"
        else:
            p = r = f1 = "n/a"
        self.lbl_metric.setText(
            f"p= {p}  r= {r}  f1= {f1}   tokens= {row.context_tokens}"
        )
        self.lbl_cost.setText(f"latency: {row.total_latency_ms:.0f} ms")

    def _render_pill(self, pill: QLabel, name: str, value: bool | None) -> None:
        text = _boolish(value)
        pill.setText(f"{name}: {text}")
        pill.setStyleSheet(PILL_BASE + f"color: {_pill_value_color(text)};")

    def _set_budget_bar(self, tokens: int) -> None:
        # Clamp to the budget so the bar never overflows its range; guarded so a Qt
        # range/value fault can't crash the panel (defensive on the off-thread path).
        ceiling = max(self.spin_budget.value(), 1)
        try:
            self.budget_bar.setValue(int(min(int(tokens), ceiling)))
        except Exception:
            self.budget_bar.setValue(0)

    # --------------------------------------------------------- tests / introspection

    def current_state(self) -> str:
        return "RUNNING" if self._active else "IDLE"

    def live_workers(self) -> list[CaseWorker]:
        return [self._worker] if self._is_live() else []

    def _is_live(self) -> bool:
        worker = self._worker
        return worker is not None and worker.isRunning()

    @property
    def last_case(self) -> CaseRun | None:
        return self._last

    # --------------------------------------------------------- backend discovery (E-11)

    def _refresh_backend(self) -> None:
        # Mirror the CLI: probe Ollama; on any failure degrade to the offline mocks and
        # say so on the banner. Never hangs, never requires a network to launch.
        if self._llm is not None and self._judge is not None:
            self._model_combo.addItem(MOCK)
            self._model_combo.setCurrentIndex(0)
            banner = "Backend: injected (offline double)"
        else:
            names = self._discover_ollama()
            self._model_combo.addItem(MOCK)
            for name in names:
                self._model_combo.addItem(name)
            index = 0
            if not self._used_fallback and names:
                index = 1 + (names.index(self._model) if self._model in names else 0)
            self._model_combo.setCurrentIndex(index)
            banner = self._banner_text()
        self.lbl_banner.setText(banner)
        if banner.startswith("Ollama unavailable"):
            self.lbl_banner.setStyleSheet("color: #c62828; font-weight: bold;")
        else:
            self.lbl_banner.setStyleSheet("color: #2e7d32;")

    def _banner_text(self) -> str:
        if self._used_fallback:
            return "Ollama unavailable -- using mock pipeline"
        return "Backend: local Ollama"

    def _discover_ollama(self) -> list[str]:
        client = self._client
        if client is None:
            client = OllamaClient(self._ollama_host)
            self._client = client
        try:
            names = client.list_models()
            self._used_fallback = len(names) == 0
            return list(names)
        except (OllamaError, ModelNotFoundError):
            self._used_fallback = True
            return []
        except Exception:
            self._used_fallback = True
            return []

    def closeEvent(self, event) -> None:
        self.cancel_run()
        worker = self._worker
        if worker is not None:
            worker.wait(1000)
            worker.deleteLater()
        super().closeEvent(event)


# ---------------------------------------------------------------------- module helpers


def _boolish(value: bool | None) -> str:
    if value is None:
        return "--"
    return "Y" if value else "N"


def _pill_value_color(text: str) -> str:
    colors = {"Y": "#2e7d32", "N": "#c62828", "--": "gray"}
    return colors.get(text, "gray")


def _pill_color(status: str) -> str:
    colors = {"SCORED": "#2e7d32", "PARTIAL": "#b26a00", "ERROR": "#c62828"}
    return PILL_BASE + f"color: {colors.get(status, 'gray')};"


def _halluc_text(unsupported: int, total: int) -> str:
    # I-007: no division by zero -- a zero-total denominator is a 0.0 rate.
    rate = (unsupported / total) if total else 0.0
    return f"hallucination: {rate:.3f}    ({unsupported}/{total})"


__all__ = ["MOCK", "CaseWorker", "MainWindow"]
