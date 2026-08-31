# pyright: reportMissingImports=false
from __future__ import annotations

import sys
from pathlib import Path


def _qt():
    from PyQt5.QtWidgets import QApplication, QComboBox, QFileDialog, QLabel, QMainWindow, QPushButton, QSpinBox, QVBoxLayout, QWidget
    return QApplication, QComboBox, QFileDialog, QLabel, QMainWindow, QPushButton, QSpinBox, QVBoxLayout, QWidget


class SynthgenWindow:
    def __new__(cls, service=None):
        QApplication, QComboBox, QFileDialog, QLabel, QMainWindow, QPushButton, QSpinBox, QVBoxLayout, QWidget = _qt()
        class Window(QMainWindow):
            def __init__(self):
                super().__init__(); self.service = service; self.setWindowTitle("synthgen")
                self.status = QLabel("Select a specification")
                self.size = QSpinBox(); self.size.setRange(1, 100); self.size.setValue(1)
                self.level = QComboBox(); self.level.addItems(["Off", "INFO", "DEBUG"])
                button = QPushButton("Preview"); button.clicked.connect(self.preview)
                layout = QVBoxLayout(); [layout.addWidget(x) for x in (self.status, self.size, self.level, button)]
                container = QWidget(); container.setLayout(layout); self.setCentralWidget(container)
            def preview(self):
                self.status.setText("Preview delegated to synthgen service")
        return Window()


def run_gui() -> int:
    QApplication, *_ = _qt()
    app = QApplication(sys.argv); window = SynthgenWindow(); window.show(); return app.exec_()
