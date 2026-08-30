import pytest

pytest.importorskip("PyQt5")

from research_agent.ui import run_gui


def test_gui_entrypoint_is_available():
    assert callable(run_gui)
