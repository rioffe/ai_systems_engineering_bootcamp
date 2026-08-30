# pyright: reportMissingImports=false
import pytest

from research_agent.schema import SchemaError, validate_document


def test_decision_schema_accepts_only_canonical_shapes():
    validate_document({"type": "tool_call", "tool": "search", "arguments": {"query": "q"}}, "decision")
    validate_document({"type": "final", "report": {"status": "ok", "answer": "a", "citations": [], "conflicts": [], "caveats": []}}, "decision")
    with pytest.raises(SchemaError):
        validate_document({"tool_call": {"tool": "search"}}, "decision")


def test_report_schema_rejects_invalid_status():
    with pytest.raises(SchemaError):
        validate_document({"status": "guess", "answer": "", "citations": [], "conflicts": [], "caveats": []}, "report")
