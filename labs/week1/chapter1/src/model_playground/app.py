"""Application entry point (SPEC R-14; pyproject script `model-playground`).

Launches the GUI: a Qt app, one `MainWindow`. Ollama is used when reachable; on any
failure the UI falls back to the built-in mock models with a status banner (E-13).
No Ollama and no keys are required to launch (the mock path is fully offline).
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    from PyQt5.QtWidgets import QApplication

    from .ui import MainWindow

    app = QApplication(argv)
    window = MainWindow()
    window.show()
    window.resize(1100, 760)
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
