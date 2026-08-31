# pyright: reportMissingImports=false
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Protocol

from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .diagnostics import configure_diagnostics
from .models import GenerationResult
from .service import preview_dataset


class PreviewService(Protocol):
    def preview(
        self, spec_path: Path, *, size: int, seed: int | None, method: str,
        model: str | None = None, host: str | None = None,
    ) -> GenerationResult: ...


class DefaultPreviewService:
    def preview(
        self, spec_path: Path, *, size: int, seed: int | None, method: str,
        model: str | None = None, host: str | None = None,
    ) -> GenerationResult:
        return preview_dataset(spec_path, size=size, seed=seed, method=method, model=model, host=host)


class SynthgenWindow(QMainWindow):
    def __init__(self, service: PreviewService | None = None) -> None:
        super().__init__()
        self.service = service or DefaultPreviewService()
        self.setWindowTitle("synthgen")
        self.resize(1000, 700)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QWidget()
        main = QHBoxLayout(root)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        form = QFormLayout()

        self.spec_input = QLineEdit(objectName="spec_input")
        self.browse_button = QPushButton("Browse...", objectName="browse_button")
        self.browse_button.clicked.connect(self.browse_spec)
        spec_row = QWidget()
        spec_layout = QHBoxLayout(spec_row)
        spec_layout.setContentsMargins(0, 0, 0, 0)
        spec_layout.addWidget(self.spec_input)
        spec_layout.addWidget(self.browse_button)
        form.addRow("Specification", spec_row)

        self.size = QSpinBox(objectName="size_input")
        self.size.setRange(1, 100)
        self.size.setValue(1)
        form.addRow("Preview records", self.size)

        self.seed_input = QLineEdit(objectName="seed_input")
        self.seed_input.setPlaceholderText("Use specification seed")
        form.addRow("Seed", self.seed_input)

        self.method = QComboBox(objectName="method_combo")
        self.method.addItems(["template", "ollama"])
        self.method.currentTextChanged.connect(self._set_ollama_controls)
        form.addRow("Realization", self.method)

        self.model_input = QLineEdit("llama3.2", objectName="model_input")
        self.host_input = QLineEdit("http://127.0.0.1:11434", objectName="host_input")
        form.addRow("Ollama model", self.model_input)
        form.addRow("Ollama host", self.host_input)

        self.level = QComboBox(objectName="verbosity_combo")
        self.level.addItems(["Off", "INFO", "DEBUG"])
        form.addRow("Diagnostics", self.level)
        left_layout.addLayout(form)

        self.preview_button = QPushButton("Preview", objectName="preview_button")
        self.preview_button.clicked.connect(self.preview)
        left_layout.addWidget(self.preview_button)
        left_layout.addStretch(1)
        self._set_ollama_controls(self.method.currentText())

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.status = QLabel("Select a specification", objectName="status_label")
        self.summary = QLabel("", objectName="summary_label")
        self.records_view = QPlainTextEdit(objectName="records_view")
        self.records_view.setReadOnly(True)
        right_layout.addWidget(QLabel("Preview records"))
        right_layout.addWidget(self.status)
        right_layout.addWidget(self.summary)
        right_layout.addWidget(self.records_view, 1)

        main.addWidget(left, 1)
        main.addWidget(right, 2)
        self.setCentralWidget(root)

    def _set_ollama_controls(self, method: str) -> None:
        visible = method == "ollama"
        self.model_input.setVisible(visible)
        self.host_input.setVisible(visible)

    def browse_spec(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self, "Select dataset specification", "", "YAML/JSON (*.yaml *.yml *.json)"
        )
        if selected:
            self.spec_input.setText(selected)

    def preview(self) -> None:
        spec_path = self.spec_input.text().strip()
        if not spec_path:
            self.status.setText("Select a specification")
            return
        try:
            seed_text = self.seed_input.text().strip()
            seed = int(seed_text) if seed_text else None
            level = self.level.currentText()
            configure_diagnostics(None if level == "Off" else level)
            self.preview_button.setEnabled(False)
            method = self.method.currentText()
            model = (self.model_input.text().strip() or None) if method == "ollama" else None
            host = (self.host_input.text().strip() or None) if method == "ollama" else None
            result = self.service.preview(
                Path(spec_path), size=self.size.value(), seed=seed, method=method,
                model=model, host=host,
            )
            self.records_view.setPlainText(
                "\n".join(json.dumps(record, sort_keys=True) for record in result.records)
            )
            report = result.report
            self.summary.setText(
                f"accepted={report.get('accepted', len(result.records))} "
                f"rejected={report.get('rejected', len(result.failures))}"
            )
            suffix = f" ({level} diagnostics)" if level != "Off" else ""
            self.status.setText(f"Preview ready: {len(result.records)} records{suffix}")
        except (OSError, TypeError, ValueError) as exc:
            self.records_view.clear()
            self.summary.clear()
            self.status.setText(f"Preview error: {exc}")
        finally:
            self.preview_button.setEnabled(True)


def run_gui() -> int:
    app = QApplication(sys.argv)
    window = SynthgenWindow()
    window.show()
    return app.exec_()
