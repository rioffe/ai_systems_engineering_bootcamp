# SPEC E-10: headless GUI testing. Force Qt's offscreen platform so the §9 GUI
# tests run in CI without a display.
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
