# pyright: reportMissingImports=false

from pathlib import Path

import pytest

pytest.importorskip("PyQt5")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QComboBox, QLabel, QLineEdit, QPushButton, QSpinBox

from synthgen.models import GenerationResult
from synthgen.ui import SynthgenWindow


class FakePreviewService:
    def __init__(self, result=None, error=None):
        self.calls = []
        self.result = result or GenerationResult(
            records=(
                {
                    "case_id": "payment-00",
                    "category": "payment",
                    "question": "What is the payment?",
                    "expected": {"outcome": "calculated"},
                },
            ),
            report={"accepted": 1, "rejected": 0, "complete": True},
            manifest={"seed": 42},
        )
        self.error = error

    def preview(self, spec_path, *, size, seed, method, model=None, host=None):
        self.calls.append({"spec_path": spec_path, "size": size, "seed": seed, "method": method, "model": model, "host": host})
        if self.error:
            raise self.error
        return self.result


def test_gui_exposes_preview_controls_and_quiet_default(qtbot):
    window = SynthgenWindow(service=FakePreviewService())
    qtbot.addWidget(window)
    assert window.windowTitle() == "synthgen"
    assert isinstance(window.spec_input, QLineEdit)
    assert isinstance(window.size, QSpinBox)
    assert isinstance(window.seed_input, QLineEdit)
    assert isinstance(window.method, QComboBox)
    assert window.model_input.text() == "llama3.2"
    assert window.host_input.text() == "http://127.0.0.1:11434"
    assert window.model_input.isHidden() is True
    assert window.host_input.isHidden() is True
    assert [window.level.itemText(i) for i in range(window.level.count())] == ["Off", "INFO", "DEBUG"]
    assert window.level.currentText() == "Off"
    assert window.model_input.text() == "llama3.2"
    assert window.host_input.text() == "http://127.0.0.1:11434"
    assert window.model_input.isHidden() is True
    assert window.host_input.isHidden() is True
    assert window.records_view.toPlainText() == ""


def test_preview_delegates_options_and_displays_jsonl_records(qtbot):
    service = FakePreviewService()
    window = SynthgenWindow(service=service)
    qtbot.addWidget(window)
    window.spec_input.setText("examples/mortgage.yaml")
    window.size.setValue(5)
    window.seed_input.setText("42")
    window.method.setCurrentText("template")
    qtbot.mouseClick(window.preview_button, Qt.LeftButton)
    assert service.calls == [{"spec_path": Path("examples/mortgage.yaml"), "size": 5, "seed": 42, "method": "template", "model": None, "host": None}]
    assert "payment-00" in window.records_view.toPlainText()
    assert "Preview ready: 1 records" == window.status.text()
    assert "accepted=1" in window.summary.text()


def test_ollama_preview_passes_selected_model_and_host(qtbot):
    service = FakePreviewService()
    window = SynthgenWindow(service=service)
    qtbot.addWidget(window)
    window.spec_input.setText("examples/mortgage.yaml")
    window.method.setCurrentText("ollama")
    assert window.model_input.isHidden() is False
    assert window.host_input.isHidden() is False
    window.model_input.setText("phi4-mini:latest")
    window.host_input.setText("http://localhost:11434")
    qtbot.mouseClick(window.preview_button, Qt.LeftButton)
    assert service.calls[0]["method"] == "ollama"
    assert service.calls[0]["model"] == "phi4-mini:latest"
    assert service.calls[0]["host"] == "http://localhost:11434"


def test_preview_requires_spec_and_surfaces_service_error(qtbot):
    window = SynthgenWindow(service=FakePreviewService(error=ValueError("bad specification")))
    qtbot.addWidget(window)
    qtbot.mouseClick(window.preview_button, Qt.LeftButton)
    assert "Select a specification" in window.status.text()
    window.spec_input.setText("bad.yaml")
    qtbot.mouseClick(window.preview_button, Qt.LeftButton)
    assert "Preview error: bad specification" == window.status.text()
