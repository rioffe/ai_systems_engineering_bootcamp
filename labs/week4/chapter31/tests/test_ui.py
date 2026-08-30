# pyright: reportMissingImports=false

import pytest

pytest.importorskip("PyQt5")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QComboBox, QLabel, QLineEdit, QTableWidget

from mortgage.ui import MainWindow


def test_window_exposes_calculator_controls(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.windowTitle() == "Hybrid Mortgage Calculator"
    assert window.findChild(QLineEdit, "principal_input") is not None
    assert window.findChild(QLineEdit, "rate_input") is not None
    assert window.findChild(QLineEdit, "term_input") is not None
    assert window.findChild(QComboBox, "model_combo") is not None
    assert window.refresh_models_button is not None
    assert window.findChild(QLabel, "payment_value") is not None
    assert window.findChild(QTableWidget, "schedule_table") is not None
    assert window.verbosity_combo.currentText() == "Off"


def test_discovery_failure_restores_refresh_and_safe_model(qtbot, monkeypatch):
    def fail(self):
        raise ValueError("MODEL_ERROR: daemon unavailable")

    monkeypatch.setattr("mortgage.ui.OllamaClient.list_models", fail)
    window = MainWindow()
    qtbot.addWidget(window)
    window.adapter_combo.setCurrentText("Ollama")
    qtbot.waitUntil(lambda: window.refresh_models_button.isEnabled(), timeout=2000)
    assert "Model discovery error" in window.status_label.text()
    assert window.model_combo.count() == 1
    assert window.model_combo.currentText() == "llama3.2"


def test_model_choices_populate_dropdown(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.set_model_choices(["llama3.2:latest", "phi4-mini:latest"])
    assert [window.model_combo.itemText(i) for i in range(window.model_combo.count())] == [
        "llama3.2:latest", "phi4-mini:latest"
    ]
    assert window.model_combo.currentText() == "llama3.2:latest"


def test_ollama_selection_queries_and_populates_models(qtbot, monkeypatch):
    monkeypatch.setattr(
        "mortgage.ui.OllamaClient.list_models",
        lambda self: ["phi4-mini:latest", "llama3.2:latest"],
    )
    window = MainWindow()
    qtbot.addWidget(window)
    window.adapter_combo.setCurrentText("Ollama")
    qtbot.waitUntil(lambda: window.model_combo.count() == 2, timeout=2000)
    assert [window.model_combo.itemText(i) for i in range(2)] == [
        "llama3.2:latest", "phi4-mini:latest"
    ]


def test_verbose_toggle_shows_diagnostics(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.verbosity_combo.setCurrentText("INFO")
    window.principal_input.setText("120")
    window.rate_input.setText("0")
    window.term_input.setText("1")
    qtbot.mouseClick(window.calculate_button, Qt.LeftButton)
    assert "verbose" in window.verbose_label.text().lower()
    assert "calculator" in window.verbose_label.text().lower()


def test_calculator_mode_renders_deterministic_result(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.principal_input.setText("500000")
    window.rate_input.setText("6.5")
    window.term_input.setText("30")
    qtbot.mouseClick(window.calculate_button, Qt.LeftButton)
    assert "3,160.34" in window.payment_value.text()
    assert "principal and interest" in window.disclaimer_label.text().lower()


def test_natural_language_request_renders_amortization_schedule(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.mode_combo.setCurrentText("Natural language")
    window.prompt_input.setPlainText("What is the payment on a $100,000 loan at 5% for 30 years?")
    window.adapter_combo.setCurrentText("Mock")
    window.include_schedule.setCurrentText("Include schedule")
    qtbot.mouseClick(window.calculate_button, Qt.LeftButton)
    assert window.schedule_table.rowCount() == 360
    assert window.schedule_table.item(0, 0).text() == "1"


def test_invalid_calculator_input_renders_error(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.principal_input.setText("-1")
    window.rate_input.setText("6.5")
    window.term_input.setText("30")
    qtbot.mouseClick(window.calculate_button, Qt.LeftButton)
    assert "Error" in window.status_label.text()


def test_mock_natural_language_mode_renders_explanation(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.mode_combo.setCurrentText("Natural language")
    window.prompt_input.setPlainText("What is the payment on $500,000 at 6.5% for 30 years?")
    window.adapter_combo.setCurrentText("Mock")
    qtbot.mouseClick(window.calculate_button, Qt.LeftButton)
    assert "3,160.34" in window.payment_value.text()
    assert window.assumptions_value.text() == "None"
