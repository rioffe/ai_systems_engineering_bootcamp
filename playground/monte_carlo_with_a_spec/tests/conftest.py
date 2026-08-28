"""Pytest bootstrap: force the Qt offscreen platform so GUI tests need no display.

(SPEC E-11.) Runs before any Qt import.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
