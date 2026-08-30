"""Optional read-only Qt artifact browser."""
from __future__ import annotations

# pyright: reportMissingImports=false
import sys


def run_gui(argv: list[str] | None = None) -> int:
    try:
        from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow
    except ImportError:
        return 2
    app = QApplication(argv or sys.argv)
    window = QMainWindow()
    window.setWindowTitle("rag-eval")
    window.setCentralWidget(QLabel("Open a validated eval artifact with rag-eval"))
    window.show()
    return app.exec_()
