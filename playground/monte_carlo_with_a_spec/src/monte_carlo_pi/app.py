"""Application entry point (SPEC R-11 / pyproject `monte-carlo-pi` console script)."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    from PyQt5.QtWidgets import QApplication

    from .ui import MainWindow

    app = QApplication(argv)
    window = MainWindow(app)
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
