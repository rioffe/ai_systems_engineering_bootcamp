"""App entry point (SPEC §5.1 / `rag-eval = rag_eval.app:main`).

A thin shim over :func:`rag_eval.cli.run`: it owns the process-level contract (parse argv,
dispatch the §5.1 subcommand, map to the documented exit codes) and exposes ``main`` for
the ``rag-eval`` console script. The logic lives in ``cli.py`` so the surface stays small.
"""

from __future__ import annotations

import sys

from .cli import run


def main(argv: list[str] | None = None) -> int:
    """The console-script entry point. Returns the documented §5.1 exit code."""
    return run(argv)


def main_gui(argv: list[str] | None = None) -> int:
    """`rag-gui` entry point: the optional PyQt5 one-question eval panel (R-13).

    Imports PyQt5 lazily so the package and the `rag-eval` CLI stay importable without a
    Qt install (I-011); the window is launched only when this surface is invoked, and it
    discovers Ollama but degrades to the offline mocks when the daemon is unreachable.
    """
    from PyQt5.QtWidgets import QApplication

    from .ui import MainWindow

    args = argv if argv is not None else sys.argv[1:]
    app = QApplication(args)
    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())


__all__ = ["main", "main_gui"]
