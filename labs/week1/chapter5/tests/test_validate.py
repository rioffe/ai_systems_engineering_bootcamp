# pyright: reportMissingImports=false
from pathlib import Path

from research_agent.tools import build_registry
from research_agent.validate import validate_decision, validate_final_report

ROOT = Path(__file__).parents[1]


def test_invalid_tool_and_argument_are_structured():
    registry = build_registry(ROOT / "corpus")
    errors = validate_decision({"type": "tool_call", "tool": "search", "arguments": {}}, registry)
    assert errors[0]["error"] == "invalid_arguments"
    assert errors[0]["field"] == "query"


def test_final_citation_and_conflict_are_checked():
    report = {"status": "ok", "answer": "a", "citations": ["missing"], "conflicts": [], "caveats": []}
    errors = validate_final_report(report, {"known"})
    assert errors and errors[0]["field"] == "citations"
