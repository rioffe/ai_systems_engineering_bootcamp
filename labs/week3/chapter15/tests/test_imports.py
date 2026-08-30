"""T-02/K-06/I-009: deterministic core has no model/network imports."""
import ast
from pathlib import Path

CORE = (
    "sandbox.py", "control_loop.py", "context.py", "tools.py", "permissions.py",
    "verifier.py", "instrument.py", "report.py",
)
FORBIDDEN = {"httpx", "requests", "urllib", "socket", "ollama", "openai"}


def test_core_source_has_no_network_imports():
    root = Path(__file__).parents[1] / "src" / "coding_agent"
    for name in CORE:
        tree = ast.parse((root / name).read_text(encoding="utf-8"), filename=name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = {alias.name.split(".")[0] for alias in node.names}
                assert not imported & FORBIDDEN, (name, imported & FORBIDDEN)
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in FORBIDDEN, (name, node.module)


def test_mock_policy_module_contains_no_socket_opening():
    source = (Path(__file__).parents[1] / "src" / "coding_agent" / "policy.py").read_text()
    assert "import socket" not in source
    assert "socket.socket" not in source
