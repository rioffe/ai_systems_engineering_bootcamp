"""UI: a side-by-side model evaluation panel (SPEC section 5 / C-07).

`MainWindow` presents the controls (prompt, parameters, model checklist) in a left
column and a grid of per-model `ModelPanel`s on the right. It performs no
inference of its own: it only configures `RunWorker`s and reacts to their queued
signals on the UI thread, so the GUI stays responsive while models generate
(R-12 / I-011 / K-01). Structured mode shows a validated-object badge plus the
parsed JSON or the collected validation errors (R-09 / R-10 / I-009).

The window can be constructed with an injected registry (used by the offscreen GUI
tests so no network is touched); otherwise it discovers Ollama and states, via a
banner, when it fell back to the mock models (E-13).
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .metrics import (
    CANCELLED,
    COMPLETED,
    ERROR,
    SUCCESS_STATUSES,
    TIMED_OUT,
    VALID,
    RunMetrics,
    cost_per_success_task,
)
from .registry import ModelRegistry, discover_registry
from .structured import ANSWER_SCHEMA, ValidationResult
from .types import Message, Role
from .worker import RunWorker

TERMINAL_STATUSES = {COMPLETED, VALID, ERROR, TIMED_OUT, CANCELLED}


class ModelPanel(QWidget):
    # A single per-model result panel (C-07): model_id, label, status, text
    # (accumulated), metrics, structured, streaming, done.

    def __init__(self, model_id: str, label: str, streaming: bool) -> None:
        super().__init__()
        self.model_id = model_id
        self.label_text = label
        self.status = "PENDING"
        self.text = ""
        self.metrics: RunMetrics | None = None
        self.structured: ValidationResult | None = None
        self.streaming = streaming
        self.done = False
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        head = QHBoxLayout()
        self.title = QLabel(self.label_text)
        self.title.setStyleSheet("font-weight: bold;")
        self.pill = QLabel(self.status)
        self.pill.setStyleSheet("color: gray;")
        head.addWidget(self.title)
        head.addStretch(1)
        head.addWidget(self.pill)
        root.addLayout(head)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setPlaceholderText("(streaming text appears here)")
        root.addWidget(self.text_edit, 1)

        grid = QGridLayout()
        self.lbl_ttft = QLabel("TTFT -- ms")
        self.lbl_latency = QLabel("Lat -- ms")
        self.lbl_tps = QLabel("TPS --")
        self.lbl_cost = QLabel("cost $0.0000")
        self.lbl_usage = QLabel("in -- / out --")
        grid.addWidget(self.lbl_ttft, 0, 0)
        grid.addWidget(self.lbl_latency, 0, 1)
        grid.addWidget(self.lbl_tps, 0, 2)
        grid.addWidget(self.lbl_cost, 0, 3)
        grid.addWidget(self.lbl_usage, 1, 0, 1, 2)
        root.addLayout(grid)

        self.lbl_structured = QLabel("structured: --")
        self.lbl_structured.setStyleSheet("color: gray;")
        root.addWidget(self.lbl_structured)

        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet("color: red;")
        root.addWidget(self.lbl_error)

    def reset(self, streaming: bool) -> None:
        self.streaming = streaming
        self.status = "PENDING"
        self.text = ""
        self.metrics = None
        self.structured = None
        self.done = False
        self.pill.setText("PENDING")
        self.pill.setStyleSheet("color: gray;")
        self._render_metrics()
        self._render_structured()
        self.lbl_error.setText("")
        self.text_edit.clear()

    def append_text(self, delta: str) -> None:
        self.text += delta
        self.text_edit.setPlainText(self.text)

    def set_metrics(self, metrics: RunMetrics) -> None:
        self.metrics = metrics
        self.status = metrics.status
        self.done = metrics.status in TERMINAL_STATUSES
        self.pill.setText(metrics.status)
        self.pill.setStyleSheet(self._pill_style(metrics.status))
        self._render_metrics()
        if metrics.status in (ERROR, TIMED_OUT, CANCELLED) and metrics.error:
            self.lbl_error.setText(metrics.error)

    def set_structured(self, result: ValidationResult) -> None:
        self.structured = result
        self._render_structured()

    def set_skipped(self) -> None:
        # A registered model that is not part of the current run: terminal, no
        # metrics shown, so the grid stays settled and consistent.
        self.status = "SKIPPED"
        self.done = True
        self.metrics = None
        self.structured = None
        self.text = ""
        self.pill.setText("SKIPPED")
        self.pill.setStyleSheet(self._pill_style("SKIPPED"))
        self._render_metrics()
        self._render_structured()
        self.lbl_error.setText("")
        self.text_edit.clear()

    def _render_metrics(self) -> None:
        m = self.metrics
        if m is None:
            self.lbl_ttft.setText("TTFT -- ms")
            self.lbl_latency.setText("Lat -- ms")
            self.lbl_tps.setText("TPS --")
            self.lbl_cost.setText("cost $0.0000")
            self.lbl_usage.setText("in -- / out --")
            return
        self.lbl_ttft.setText(f"TTFT {m.ttft_ms:.0f} ms")
        self.lbl_latency.setText(f"Lat {m.total_latency_ms:.0f} ms")
        self.lbl_tps.setText(f"TPS {m.tps:.1f}")
        self.lbl_cost.setText(f"cost ${m.cost_usd:.4f}")
        self.lbl_usage.setText(
            f"in {m.usage.prompt_tokens} / out {m.usage.completion_tokens}"
        )

    def _render_structured(self) -> None:
        vr = self.structured
        if vr is None:
            self.lbl_structured.setText("structured: --")
            self.lbl_structured.setStyleSheet("color: gray;")
            return
        if vr.ok:
            self.lbl_structured.setText(f"structured: OK    {vr.data}")
            self.lbl_structured.setStyleSheet("color: green;")
            return
        self.lbl_structured.setText(f"structured: FAIL    {vr.errors}")
        self.lbl_structured.setStyleSheet("color: red;")

    @staticmethod
    def _pill_style(status: str) -> str:
        base = "font-weight: bold; padding: 1px 6px; border: 1px solid; "
        colors = {
            COMPLETED: "#2e7d32",
            VALID: "#1565c0",
            ERROR: "#c62828",
            TIMED_OUT: "#c62828",
            CANCELLED: "#8d6e6e",
            "STREAMING": "#8d6e6e",
            "PENDING": "gray",
            "IDLE": "gray",
            "SKIPPED": "gray",
        }
        return base + f"color: {colors.get(status, 'gray')};"


class MainWindow(QMainWindow):
    run_settled = pyqtSignal()

    def __init__(
        self,
        app=None,
        registry: ModelRegistry | None = None,
        used_fallback: bool = False,
        ollama_host: str | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Model Playground -- an inference substrate")

        self.registry = registry
        self._used_fallback = used_fallback
        if registry is None:
            self.registry, self._used_fallback = discover_registry(ollama_host)

        self._panels: dict[str, ModelPanel] = {}
        self._workers: dict[str, RunWorker] = {}
        self._total = 0
        self._finished = 0
        self._queued: list[str] = []
        self._active = False

        self._build_ui()
        self._precreate_panels()
        self._update_running()

    def _precreate_panels(self) -> None:
        # Populate the side-by-side grid at launch with one panel per pre-selected
        # model (SPEC section 5.1), so the right column is never an empty box.
        for mid, box in self._model_boxes.items():
            if box.isChecked() and mid not in self._panels:
                spec = self.registry.get(mid)
                self.add_panel(mid, spec.display_label)

        # --------------------------------------------------------- UI layout

    def _build_ui(self) -> None:
        left = self._build_controls()

        panel_group = QGroupBox("Models (side by side)")
        self._panel_stack = QScrollArea()
        self._panel_stack.setWidgetResizable(True)
        self._panel_stack_inner = QWidget()
        self._panel_stack_inner_layout = QVBoxLayout(self._panel_stack_inner)
        self._panel_stack_inner_layout.addStretch(1)
        self._panel_stack.setWidget(self._panel_stack_inner)
        panel_group.setContentsMargins(0, 0, 0, 0)
        panel_layout = QVBoxLayout(panel_group)
        # The group box paints its title in the top frame region; keep the
        # panels filling the column's width horizontally, but reserve the title
        # height up top so the first panel doesn't render over ``Models
        # (side by side)``.
        title_h = panel_group.fontMetrics().height()
        panel_layout.setContentsMargins(0, title_h + 8, 0, 0)
        panel_layout.addWidget(self._panel_stack)

        splitter = QHBoxLayout()
        splitter.addWidget(left)
        splitter.addWidget(panel_group, 1)
        central = QWidget()
        central.setLayout(splitter)
        self.setCentralWidget(central)

    def _build_controls(self) -> QWidget:
        w = QWidget()
        box = QVBoxLayout(w)

        self.lbl_banner = QLabel("")
        box.addWidget(self.lbl_banner)
        self._refresh_banner()

        box.addWidget(QLabel("Prompt"))
        self.prompt = QPlainTextEdit()
        self.prompt.setPlaceholderText("Enter a prompt (required).")
        self.prompt.textChanged.connect(self._validate)
        box.addWidget(self.prompt)

        box.addWidget(QLabel("System prompt (optional)"))
        self.system_prompt = QPlainTextEdit()
        self.system_prompt.setFixedHeight(60)
        self.system_prompt.textChanged.connect(self._validate)
        box.addWidget(self.system_prompt)

        grid = QGridLayout()
        self.spin_temp = QDoubleSpinBox()
        self.spin_temp.setRange(0.0, 2.0)
        self.spin_temp.setSingleStep(0.1)
        self.spin_temp.setValue(0.0)
        self.spin_top_p = QDoubleSpinBox()
        self.spin_top_p.setRange(0.001, 1.0)
        self.spin_top_p.setSingleStep(0.05)
        self.spin_top_p.setValue(1.0)
        self.spin_max_tokens = QSpinBox()
        self.spin_max_tokens.setRange(1, 100_000)
        self.spin_max_tokens.setValue(512)
        self.edit_seed = QLineEdit()
        self.edit_seed.setPlaceholderText("blank = random")
        for row, (label, widget) in enumerate(
            [
                ("Temperature", self.spin_temp),
                ("top_p", self.spin_top_p),
                ("max_tokens", self.spin_max_tokens),
                ("seed", self.edit_seed),
            ]
        ):
            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(widget, row, 1)
        for widget in (self.spin_temp, self.spin_top_p, self.spin_max_tokens):
            widget.valueChanged.connect(self._validate)
        self.edit_seed.textChanged.connect(self._validate)
        box.addLayout(grid)

        self.chk_stream = QCheckBox("Stream (show TTFT per token)")
        self.chk_structured = QCheckBox("Structured output (validate JSON)")
        self.chk_sequential = QCheckBox("Sequential (one model at a time)")
        self.chk_stream.setChecked(True)
        box.addWidget(self.chk_stream)
        box.addWidget(self.chk_structured)
        box.addWidget(self.chk_sequential)

        box.addWidget(QLabel("Models"))
        self._model_boxes: dict[str, QCheckBox] = {}
        for spec in self.registry.available():
            box_key = QCheckBox(spec.display_label)
            box_key.setChecked(spec.model.model_id in ("mock/fast", "mock/slow"))
            self._model_boxes[spec.model.model_id] = box_key
            box_key.stateChanged.connect(self._validate)
            box.addWidget(box_key)

        row = QHBoxLayout()
        self.btn_run = QPushButton("Run")
        self.btn_cancel = QPushButton("Cancel")
        row.addWidget(self.btn_run)
        row.addWidget(self.btn_cancel)
        row.addStretch(1)
        box.addLayout(row)
        self.btn_run.clicked.connect(self.on_run)
        self.btn_cancel.clicked.connect(self.on_cancel)

        self.lbl_message = QLabel("")
        box.addWidget(self.lbl_message)
        self.lbl_state = QLabel("state: IDLE")
        box.addWidget(self.lbl_state)
        self.lbl_cost_task = QLabel("cost/task: --")
        box.addWidget(self.lbl_cost_task)

        return w

    def add_panel(self, model_id: str, label: str) -> None:
        panel = ModelPanel(model_id, label, streaming=self.chk_stream.isChecked())
        self._panels[model_id] = panel
        self._panel_stack_inner_layout.insertWidget(0, panel)

        # --------------------------------------------------------- validation

    def _validate(self, *_args) -> bool:
        ok = True
        message = ""

        prompt = self.prompt.toPlainText().strip()
        if prompt == "":
            ok = False
            message = "Prompt must not be empty"

        models = [mid for mid, box in self._model_boxes.items() if box.isChecked()]
        if ok and len(models) == 0:
            ok = False
            message = "Select at least one model"

        seed_text = self.edit_seed.text().strip()
        if ok and seed_text != "" and self._seed_value() is None:
            ok = False
            message = "Seed must be an integer or blank"

        if ok and self.spin_max_tokens.value() < 1:
            ok = False
            message = "max_tokens must be >= 1"

        self.lbl_message.setText(message)
        if not self._active:
            self.btn_run.setEnabled(ok)
        return ok

    def _seed_value(self) -> int | None:
        text = self.edit_seed.text().strip()
        if text == "":
            return None
        try:
            return int(text)
        except ValueError:
            return None

    def _build_messages(self) -> list[Message]:
        messages: list[Message] = []
        system = self.system_prompt.toPlainText().strip()
        if system:
            messages.append(Message(Role.SYSTEM, system))
        messages.append(Message(Role.USER, self.prompt.toPlainText().strip()))
        return messages

    def _params(self) -> dict:
        return {
            "temperature": self.spin_temp.value(),
            "top_p": self.spin_top_p.value(),
            "max_tokens": self.spin_max_tokens.value(),
            "seed": self._seed_value(),
        }

        # --------------------------------------------------------- actions

    def on_run(self) -> None:
        if not self._validate():
            return
        self.cancel_run()
        self._active = True
        self._finished = 0
        self._messages = self._build_messages()
        self._params_bag = self._params()
        self._structured = self.chk_structured.isChecked()
        self._streaming = self.chk_stream.isChecked()
        self._sequential = self.chk_sequential.isChecked()
        self._update_running()

        selected = [mid for mid, box in self._model_boxes.items() if box.isChecked()]
        if not selected:
            self._active = False
            self._update_running()
            return
        self._total = len(selected)
        self._finished = 0
        # Reset every shown panel; unselected ones are marked SKIPPED so the grid
        # stays settled and consistent even when a model is not in this run.
        for panel_id, panel in list(self._panels.items()):
            if panel_id not in selected:
                panel.set_skipped()
                continue
        for mid in selected:
            spec = self.registry.get(mid)
            if mid not in self._panels:
                self.add_panel(mid, spec.display_label)
            self._panels[mid].reset(self._streaming)

        if self._sequential:
            self._queued = selected
            self._spawn(self._queued.pop(0))
        else:
            for panel_id in selected:
                self._spawn(panel_id)

    def on_cancel(self) -> None:
        self.cancel_run()

    def cancel_run(self) -> None:
        self._active = False
        self._queued = []
        for worker in list(self._workers.values()):
            worker.cancel()
        self._update_running()

        # ------------------------------------------------ spawn / settle

    def _spawn(self, panel_id: str) -> None:
        spec = self.registry.get(panel_id)
        worker = RunWorker(
            spec.model,
            panel_id,
            self.registry,
            schema=ANSWER_SCHEMA,
            structured_mode=self._structured,
            streaming=self._streaming,
        )
        self._panels[panel_id].status = "PENDING"
        worker.token.connect(self._on_token)
        worker.metrics_ready.connect(self._on_metrics)
        worker.structured.connect(self._on_structured)
        worker.crashed.connect(self._on_crashed)
        worker.finished.connect(lambda _mid=panel_id: self._on_worker_finished(_mid))
        self._workers[panel_id] = worker
        worker.start_run(self._messages, self._params_bag)

    def _on_token(self, panel_id: str, delta: str) -> None:
        panel = self._panels.get(panel_id)
        if panel is not None:
            panel.append_text(delta)
            panel.status = "STREAMING"
            panel.pill.setText("STREAMING")
            panel.pill.setStyleSheet("color: #8d6e6e;")

    def _on_metrics(self, panel_id: str, metrics: RunMetrics) -> None:
        panel = self._panels.get(panel_id)
        if panel is None:
            return
        panel.set_metrics(metrics)
        self._refresh_cost_task()

    def _on_structured(self, panel_id: str, result: ValidationResult) -> None:
        panel = self._panels.get(panel_id)
        if panel is not None:
            panel.set_structured(result)

    def _on_crashed(self, panel_id: str, message: str) -> None:
        panel = self._panels.get(panel_id)
        if panel is not None:
            panel.lbl_error.setText(message)
            panel.status = "ERROR"

    def _on_worker_finished(self, panel_id: str) -> None:
        self._workers.pop(panel_id, None)
        self._finished += 1
        if not self._active:
            self._settle_if_done()
            return
        if self._queued:
            self._spawn(self._queued.pop(0))
        self._settle_if_done()

    def _settle_if_done(self) -> None:
        if self._queued or self._workers:
            return
        if self._total > 0 and self._finished >= self._total:
            self._active = False
            self._refresh_cost_task()
            self._update_running()
            self.run_settled.emit()

            # --------------------------------------------------------- helpers

    def _update_running(self) -> None:
        running = self._active
        self.btn_run.setEnabled((not running) and self._validate())
        self.btn_cancel.setEnabled(running)
        self.lbl_state.setText("state: RUNNING" if running else "state: IDLE")

    def current_state(self) -> str:
        return "RUNNING" if self._active else "IDLE"

    def _refresh_cost_task(self) -> None:
        values = [
            p.metrics.cost_usd for p in self._panels.values() if p.metrics is not None
        ]
        total_cost = sum(values)
        success = sum(
            1
            for panel in self._panels.values()
            if panel.metrics is not None and panel.metrics.status in SUCCESS_STATUSES
        )
        settled = sum(1 for p in self._panels.values() if p.done)
        value = cost_per_success_task(total_cost, success)
        self.lbl_cost_task.setText(
            f"cost/task: ${value:.4f}    ({success} ok / {settled} settled)"
        )

    def _refresh_banner(self) -> None:
        if self._used_fallback:
            self.lbl_banner.setText("Ollama unavailable -- using mock models")
            self.lbl_banner.setStyleSheet("color: #c62828; font-weight: bold;")
        else:
            self.lbl_banner.setText("Backend: local Ollama")
            self.lbl_banner.setStyleSheet("color: #2e7d32;")

    def panels(self) -> dict[str, ModelPanel]:
        return self._panels

    def live_workers(self) -> list[RunWorker]:
        return list(self._workers.values())

    @property
    def used_fallback(self) -> bool:
        return self._used_fallback

    def closeEvent(self, event) -> None:
        self.cancel_run()
        for worker in list(self._workers.values()):
            worker.wait(1000)
        super().closeEvent(event)


__all__ = ["MAIN_WINDOW_AVAILABLE", "MainWindow", "ModelPanel"]
MAIN_WINDOW_AVAILABLE = True
