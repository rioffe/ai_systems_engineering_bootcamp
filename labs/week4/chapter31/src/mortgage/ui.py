# pyright: reportMissingImports=false

from __future__ import annotations

import sys
from decimal import Decimal, InvalidOperation
from typing import Any

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .llm import MockLLMAdapter, OllamaAdapter
from .models import CalculationRequest
from .presentation import DISCLAIMER
from .service import calculate


class OllamaWorker(QThread):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, text: str, model: str, host: str) -> None:
        super().__init__()
        self.text = text
        self.model = model
        self.host = host

    def run(self) -> None:
        try:
            self.completed.emit(OllamaAdapter(model=self.model, host=self.host).ask(self.text))
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Hybrid Mortgage Calculator")
        self.resize(1100, 720)
        self._worker: OllamaWorker | None = None
        self._build_ui()
        self._set_mode("Calculator")

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QHBoxLayout(root)
        controls = self._build_controls()
        results = self._build_results()
        layout.addWidget(controls, 1)
        layout.addWidget(results, 2)
        self.setCentralWidget(root)

    def _build_controls(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        mode_box = QGroupBox("Mode")
        mode_layout = QFormLayout(mode_box)
        self.mode_combo = QComboBox(objectName="mode_combo")
        self.mode_combo.addItems(["Calculator", "Natural language"])
        self.mode_combo.currentTextChanged.connect(self._set_mode)
        mode_layout.addRow("Input mode", self.mode_combo)
        layout.addWidget(mode_box)

        self.calculator_box = QGroupBox("Mortgage inputs")
        form = QFormLayout(self.calculator_box)
        self.principal_input = QLineEdit(objectName="principal_input")
        self.rate_input = QLineEdit(objectName="rate_input")
        self.rate_period_combo = QComboBox(objectName="rate_period_combo")
        self.rate_period_combo.addItems(["Annual percentage", "Monthly decimal"])
        self.term_input = QLineEdit(objectName="term_input")
        self.payments_input = QLineEdit(objectName="payments_input")
        self.payment_input = QLineEdit(objectName="payment_input")
        form.addRow("Principal", self.principal_input)
        form.addRow("Rate", self.rate_input)
        form.addRow("Rate units", self.rate_period_combo)
        form.addRow("Term (years)", self.term_input)
        form.addRow("Payments", self.payments_input)
        form.addRow("Payment", self.payment_input)
        layout.addWidget(self.calculator_box)

        self.language_box = QGroupBox("Natural-language question")
        language_form = QFormLayout(self.language_box)
        self.prompt_input = QPlainTextEdit(objectName="prompt_input")
        self.prompt_input.setPlaceholderText("Ask a mortgage question...")
        self.prompt_input.setMaximumHeight(130)
        self.adapter_combo = QComboBox(objectName="adapter_combo")
        self.adapter_combo.addItems(["Mock", "Ollama"])
        self.model_input = QLineEdit("llama3.2", objectName="model_input")
        self.host_input = QLineEdit("http://localhost:11434", objectName="host_input")
        language_form.addRow("Question", self.prompt_input)
        language_form.addRow("Adapter", self.adapter_combo)
        language_form.addRow("Model", self.model_input)
        language_form.addRow("Ollama host", self.host_input)
        layout.addWidget(self.language_box)

        options = QGroupBox("Options")
        options_layout = QFormLayout(options)
        self.include_schedule = QComboBox(objectName="schedule_combo")
        self.include_schedule.addItems(["No schedule", "Include schedule"])
        self.rounding_input = QSpinBox(objectName="rounding_input")
        self.rounding_input.setRange(0, 10)
        self.rounding_input.setValue(2)
        options_layout.addRow("Amortization", self.include_schedule)
        options_layout.addRow("Display decimals", self.rounding_input)
        layout.addWidget(options)

        self.calculate_button = QPushButton("Calculate", objectName="calculate_button")
        self.calculate_button.clicked.connect(self._on_calculate)
        layout.addWidget(self.calculate_button)
        layout.addStretch(1)
        return panel

    def _build_results(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        title = QLabel("Validated result")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)

        metrics = QGridLayout()
        self.payment_value = QLabel("—", objectName="payment_value")
        self.principal_value = QLabel("—", objectName="principal_value")
        self.rate_value = QLabel("—", objectName="rate_value")
        self.term_value = QLabel("—", objectName="term_value")
        self.total_value = QLabel("—", objectName="total_value")
        self.interest_value = QLabel("—", objectName="interest_value")
        for row, (label, widget) in enumerate(
            (("Monthly payment", self.payment_value), ("Principal", self.principal_value),
             ("Annual rate", self.rate_value), ("Term", self.term_value),
             ("Total paid", self.total_value), ("Total interest", self.interest_value))
        ):
            metrics.addWidget(QLabel(label), row // 2, (row % 2) * 2)
            metrics.addWidget(widget, row // 2, (row % 2) * 2 + 1)
        layout.addLayout(metrics)

        self.status_label = QLabel("Ready", objectName="status_label")
        self.assumptions_value = QLabel("None", objectName="assumptions_value")
        self.explanation_label = QLabel("", objectName="explanation_label")
        self.explanation_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        layout.addWidget(QLabel("Assumptions"))
        layout.addWidget(self.assumptions_value)
        layout.addWidget(self.explanation_label)

        self.schedule_table = QTableWidget(objectName="schedule_table")
        self.schedule_table.setColumnCount(6)
        self.schedule_table.setHorizontalHeaderLabels(["Period", "Payment", "Principal", "Interest", "Balance", "Adjusted"])
        layout.addWidget(self.schedule_table, 1)
        self.disclaimer_label = QLabel(DISCLAIMER, objectName="disclaimer_label")
        self.disclaimer_label.setWordWrap(True)
        self.disclaimer_label.setStyleSheet("color: #555; font-size: 11px;")
        layout.addWidget(self.disclaimer_label)
        return panel

    def _set_mode(self, mode: str) -> None:
        calculator = mode == "Calculator"
        self.calculator_box.setVisible(calculator)
        self.language_box.setVisible(not calculator)

    @staticmethod
    def _decimal(value: str, name: str) -> Decimal:
        try:
            result = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"{name} must be numeric") from exc
        if not result.is_finite():
            raise ValueError(f"{name} must be finite")
        return result

    @staticmethod
    def _integer(value: str, name: str) -> int:
        try:
            return int(value)
        except (TypeError, ValueError, ArithmeticError) as exc:
            raise ValueError(f"{name} must be an integer") from exc

    def _calculator_request(self) -> CalculationRequest:
        principal = self._decimal(self.principal_input.text(), "principal") if self.principal_input.text() else None
        rate = self._decimal(self.rate_input.text(), "rate") if self.rate_input.text() else None
        periodic_rate = None
        if rate is not None:
            periodic_rate = rate / Decimal(1200) if self.rate_period_combo.currentIndex() == 0 else rate
        payments = self._integer(self.payments_input.text(), "payments") if self.payments_input.text() else None
        if self.term_input.text():
            years = self._decimal(self.term_input.text(), "term")
            candidate = years * Decimal(12)
            if candidate != candidate.to_integral_value():
                raise ValueError("term must convert to whole monthly payments")
            if payments is not None:
                raise ValueError("payments and term cannot both be supplied")
            payments = self._integer(str(candidate), "term")
        payment = self._decimal(self.payment_input.text(), "payment") if self.payment_input.text() else None
        return CalculationRequest(principal, periodic_rate, payments, payment, self.include_schedule.currentIndex() == 1)

    def _on_calculate(self) -> None:
        try:
            if self.mode_combo.currentText() == "Natural language":
                if self.adapter_combo.currentText() == "Ollama":
                    self.calculate_button.setEnabled(False)
                    self._worker = OllamaWorker(self.prompt_input.toPlainText(), self.model_input.text(), self.host_input.text())
                    self._worker.completed.connect(self._show_adapter_response)
                    self._worker.failed.connect(self._show_worker_error)
                    self._worker.finished.connect(lambda: self.calculate_button.setEnabled(True))
                    self._worker.start()
                else:
                    self._show_adapter_response(MockLLMAdapter().ask(self.prompt_input.toPlainText()))
                return
            self._show_payload(calculate(self._calculator_request(), adapter="direct"))
        except (TypeError, ValueError) as exc:
            self.status_label.setText(f"Error: {exc}")

    def _show_worker_error(self, message: str) -> None:
        self.status_label.setText(f"Error: {message}")

    def _show_adapter_response(self, response: Any) -> None:
        if response.interpretation.clarification and response.result is None:
            self.status_label.setText("Clarification required")
            self.explanation_label.setText(response.interpretation.clarification)
            return
        if response.error is not None:
            self.status_label.setText(f"Error: {response.error['code']}")
            self.explanation_label.setText(response.error["message"])
            return
        self._show_result_dict(response.result, response.interpretation.assumptions)
        self.explanation_label.setText(response.explanation or "")

    def _show_payload(self, payload: dict[str, Any]) -> None:
        if not payload["ok"]:
            self.status_label.setText(f"Error: {payload['error'].code}")
            self.explanation_label.setText(payload["error"].message)
            return
        self._show_result_object(payload["result"], payload["metadata"].assumptions)

    def _show_result_object(self, result: Any, assumptions: tuple[str, ...]) -> None:
        self.status_label.setText("Calculated")
        self.payment_value.setText(f"${result.payment:,.2f}")
        self.principal_value.setText(f"${result.principal:,.2f}")
        self.rate_value.setText(f"{result.annual_rate * 100:.4f}%")
        self.term_value.setText(f"{result.term_years:g} years")
        self.total_value.setText(f"${result.total_paid:,.2f}")
        self.interest_value.setText(f"${result.total_interest:,.2f}")
        self.assumptions_value.setText("; ".join(assumptions) if assumptions else "None")
        self._show_schedule(result.schedule)

    def _show_result_dict(self, result: dict[str, Any], assumptions: tuple[str, ...]) -> None:
        self.status_label.setText("Calculated")
        self.payment_value.setText(f"${Decimal(result['payment']):,.2f}")
        self.principal_value.setText(f"${Decimal(result['principal']):,.2f}")
        self.rate_value.setText(f"{Decimal(result['annual_rate']) * 100:.4f}%")
        self.term_value.setText(f"{Decimal(result['term_years']):g} years")
        self.total_value.setText(f"${Decimal(result['total_paid']):,.2f}")
        self.interest_value.setText(f"${Decimal(result['total_interest']):,.2f}")
        self.assumptions_value.setText("; ".join(assumptions) if assumptions else "None")
        self._show_schedule(None)

    def _show_schedule(self, schedule: Any) -> None:
        rows = schedule or ()
        self.schedule_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = (row.period, row.payment, row.principal, row.interest, row.balance, row.adjusted_payoff)
            for column, value in enumerate(values):
                self.schedule_table.setItem(row_index, column, QTableWidgetItem(f"{value:,.2f}" if isinstance(value, Decimal) else str(value)))


def run_gui(argv: list[str] | None = None) -> int:
    app = QApplication(argv or sys.argv)
    window = MainWindow()
    window.show()
    return app.exec_()
