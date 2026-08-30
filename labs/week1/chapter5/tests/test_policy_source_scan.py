from pathlib import Path


def test_only_policy_imports_http_client():
    root = Path(__file__).parents[1] / "src" / "research_agent"
    for path in root.glob("*.py"):
        if path.name != "policy.py":
            assert "import httpx" not in path.read_text()
