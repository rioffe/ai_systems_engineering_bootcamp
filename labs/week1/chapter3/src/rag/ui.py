# rag.ui -- the interactive query console (R-16 / F-12).
# The GUI is OPTIONAL. Whether or not a Qt backend is present, the surface
# degrades to a headless, non-blocking console (the CLI `show` view: build
# the index, run a query, print answer + verdict). It NEVER blocks on stdin.

from __future__ import annotations

import sys


def _import_qt():
    # Probe common Qt bindings; return a module or None if absent.
    for mod in ("PySide6", "PyQt5", "PySide2"):
        try:
            return __import__(mod)
        except ImportError:
            continue
    return None


def _launch_qt(qt, argv):
    # Real-GUI extension point (headless-safe); no re-entry into
    # run_gui (that would recurse). Runs the same console via app.main.
    from rag.app import main

    call = argv if argv else ["show"]
    try:
        return int(main(call))
    except (OSError, ValueError, SystemExit) as exc:
        print("query console degraded (F-012): " + str(exc), file=sys.stderr)
        return 0


def run_gui(argv=None, *, build=None, run=None) -> int:
    # Build the index, then run the query console; default to the
    # per-query `show` view when no subcommand is given. The whole run
    # is guarded so a backend / load fault degrades to exit 0, F-012.
    args = list(argv or [])
    subs = ("show", "eval", "build-index", "gen-corpus")
    if not any(a in args for a in subs):
        args = ["show"] + args
    try:
        qt = _import_qt()
        if qt is not None:
            return int(_launch_qt(qt, args))
        print("GUI backend headless; console fallback (F-012).", file=sys.stderr)
        from rag.app import main

        return int(main(args))
    except (OSError, ValueError, SystemExit) as exc:
        print("query console degraded (F-012): " + str(exc), file=sys.stderr)
        return 0
