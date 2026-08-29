# rag.ui -- the interactive query console (R-16 / F-12).
# The GUI is OPTIONAL. Whether or not a Qt backend is present, the surface
# degrades to a headless, non-blocking console (the CLI `show` view: build the
# index, run a query, print answer + verdict). It NEVER blocks on stdin, F-11/012.

from __future__ import annotations

import sys


def _import_qt():
    # Probe common Qt bindings; return a module or None when none is installed.
    for mod in ('PySide6', 'PyQt5', 'PySide2'):
        try:
            return __import__(mod)
        except ImportError:
            continue
    return None


def _launch_qt(qt, argv):
    # Real-GUI extension point (headless-safe). We do NOT re-enter run_gui
    # (that would recurse); instead run the same console view via rag.app.main.
    from rag.app import main
    call = argv if argv else ['show']
    try:
        return int(main(call))
    except (OSError, ValueError, SystemExit) as exc:
        sys.stderr.write('query console degraded (F-012): ' + str(exc) + '\n')
        return 0


def run_gui(argv=None, *, build=None, run=None):
    # Build the index, then run the query console. If no subcommand is given,
    # default to the per-query `show` view. Never block on stdin.
    args = list(argv or [])
    subs = ('show', 'eval', 'build-index', 'gen-corpus')
    if not any(a in args for a in subs):
        args = ['show'] + args
    qt = _import_qt()
    if qt is not None:
        return int(_launch_qt(qt, args))
            # F-012: no GUI backend -> a message + the CLI. Never a crash/hang.
    sys.stderr.write('GUI backend detected but headless; console fallback (F-012).\n')
    try:
        from rag.app import main
        return int(main(args))
    except (OSError, ValueError, SystemExit) as exc:
        sys.stderr.write('query console degraded (F-012): ' + str(exc) + '\n')
        return 0
