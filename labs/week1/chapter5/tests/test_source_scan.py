from pathlib import Path


def test_deterministic_core_has_no_network_imports():
    root = Path(__file__).parents[1] / "src" / "research_agent"
    forbidden = ("import httpx", "from httpx", "import ollama", "from ollama")
    core = ("state.py", "tools.py", "validate.py", "authorize.py", "budgets.py", "retry.py", "trace.py", "metrics.py", "drills.py", "report.py", "runtime.py")
    for name in core:
        assert not any(token in (root / name).read_text() for token in forbidden), name
