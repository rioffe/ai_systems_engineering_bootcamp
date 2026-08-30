# pyright: reportMissingImports=false
from pathlib import Path

import pytest

from research_agent.config import DEFAULT_BUDGETS, ConfigError, load_budgets, load_policy


def test_defaults_and_policy():
    assert load_budgets() == DEFAULT_BUDGETS
    assert load_policy()["default"] == "deny"


def test_unknown_budget_key_rejected(tmp_path: Path):
    path = tmp_path / "budgets.yml"
    path.write_text("max_steps: 2\nunknown: true\n")
    with pytest.raises(ConfigError):
        load_budgets(path)
