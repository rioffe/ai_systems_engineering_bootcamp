"""Optional read-only trace browser."""
from __future__ import annotations

import sys


def run_gui(argv: list[str] | None = None) -> int:
    try:
        from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow
    except ImportError:
        return 2
    app = QApplication(argv or sys.argv)
    window = QMainWindow()
    window.setWindowTitle("research-agent")
    window.setCentralWidget(QLabel("Use research-agent trace <trace.json> to inspect a trace."))
    window.show()
    return app.exec_()
