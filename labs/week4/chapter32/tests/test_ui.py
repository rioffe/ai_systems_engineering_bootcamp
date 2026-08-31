# pyright: reportMissingImports=false

import pytest

pytest.importorskip("PyQt5")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QComboBox, QLabel, QPushButton, QSpinBox

from synthgen.ui import SynthgenWindow


def test_synthgen_gui_constructs_with_required_controls(qtbot):
    window = SynthgenWindow()
    qtbot.addWidget(window)
    assert window.windowTitle() == "synthgen"
    assert isinstance(window.status, QLabel)
    assert isinstance(window.size, QSpinBox)
    assert isinstance(window.level, QComboBox)
    assert [window.level.itemText(i) for i in range(window.level.count())] == [
        "Off", "INFO", "DEBUG"
    ]
    assert window.findChild(QPushButton).text() == "Preview"


def test_synthgen_gui_preview_delegates_to_service(qtbot):
    window = SynthgenWindow()
    qtbot.addWidget(window)
    qtbot.mouseClick(window.findChild(QPushButton), Qt.LeftButton)
    assert window.status.text() == "Preview delegated to synthgen service"
