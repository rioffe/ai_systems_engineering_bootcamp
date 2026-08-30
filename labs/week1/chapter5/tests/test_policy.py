# pyright: reportMissingImports=false
from research_agent.policy import MockPolicy


def test_mock_policy_search_retrieve_final():
    policy = MockPolicy()
    tools = []
    first = policy.decide({"goal": "reimbursement limit", "observations": []}, tools)
    assert first["type"] == "tool_call" and first["tool"] == "search"
    second = policy.decide({"goal": "reimbursement limit", "observations": [{"tool": "search", "result": [{"doc_id": "d"}]}]}, tools)
    assert second["tool"] == "retrieve"
    third = policy.decide({"goal": "q", "observations": [{"tool": "search", "result": [{"doc_id": "d"}]}, {"tool": "retrieve", "result": {"doc_id": "d"}}]}, tools)
    assert third["type"] == "final"
