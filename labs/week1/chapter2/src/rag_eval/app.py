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


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())


__all__ = ["main"]
