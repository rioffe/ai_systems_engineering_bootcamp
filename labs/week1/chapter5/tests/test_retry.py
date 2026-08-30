# pyright: reportMissingImports=false
from research_agent.retry import FailureClass, classify_error, execute_with_retry
from research_agent.tools import PermanentError, TransientError


def test_retry_only_transient_and_total_classes():
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) == 1:
            raise TransientError("timeout")
        return {"ok": True}

    result = execute_with_retry(flaky, max_retries=2)
    assert result.result == {"ok": True} and result.retries == 1
    assert classify_error(PermanentError("missing")) == FailureClass.PERMANENT
