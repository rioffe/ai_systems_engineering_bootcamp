# pyright: reportMissingImports=false

from rag_eval.failure import classify_failure


def test_failure_precedence_and_fallback():
    assert classify_failure("PARSE_BLOCKED", "generation", "q") == "PARSING_FAILURE"
    assert classify_failure("FAIL", "expansion", "q") == "RETRIEVAL_FAILURE"
    assert classify_failure("FAIL", "context", "q") == "CONTEXT_FAILURE"
    assert classify_failure("FAIL", "generation", "q") == "GENERATION_FAILURE"
    assert classify_failure("FAIL", None, "q") == "GENERATION_FAILURE"
    assert classify_failure("FAIL", "generation", "q", {"q"}) == "EVALUATION_FAILURE"
    assert classify_failure("PASS", None, "q") is None
