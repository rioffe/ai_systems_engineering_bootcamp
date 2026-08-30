# pyright: reportMissingImports=false

import pytest

pytest.importorskip("PyQt5")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel, QLineEdit, QTableWidget

from mortgage.ui import MainWindow


def test_window_exposes_calculator_controls(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.windowTitle() == "Hybrid Mortgage Calculator"
    assert window.findChild(QLineEdit, "principal_input") is not None
    assert window.findChild(QLineEdit, "rate_input") is not None
    assert window.findChild(QLineEdit, "term_input") is not None
    assert window.findChild(QLabel, "payment_value") is not None
    assert window.findChild(QTableWidget, "schedule_table") is not None


def test_calculator_mode_renders_deterministic_result(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.principal_input.setText("500000")
    window.rate_input.setText("6.5")
    window.term_input.setText("30")
    qtbot.mouseClick(window.calculate_button, Qt.LeftButton)
    assert "3,160.34" in window.payment_value.text()
    assert "principal and interest" in window.disclaimer_label.text().lower()


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
