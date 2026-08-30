# pyright: reportMissingImports=false
from research_agent.authorize import AuthorizationEngine


def test_default_deny_and_explicit_rules():
    engine = AuthorizationEngine({"rules": [{"tool": "search", "effect": "allow"}], "default": "deny"})
    assert engine.authorize("search", {}).allowed
    assert not engine.authorize("delete_file", {}).allowed
