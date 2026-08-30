"""C-02 / R-14 / K-06 the Policy interface and its two implementations.

The `Policy` interface is the ONLY boundary where the model may be reached
(R-15 / I-009). `MockPolicy` is a deterministic offline double (no network);
`OllamaPolicy` is the opt-in real path that is the SOLE module that MAY import a
network client -- and only lazily, so `import coding_agent.policy` never opens a
socket (K-06 / T-02).

`resolve()` is the model-availability taxonomy (R-14 / E-11-E-12): DEGRADED_MOCK
(daemon unreachable -> offline mock, banner, exit 0), PULL_REQUIRED (model absent
-> remediation string, exit 4), RUN_REAL (present -> real policy, no banner,
exit 0) -- resolved by an injectable probe so the suite needs no Ollama.
"""

import sys

import pytest

from coding_agent.policy import (
    NOOP,
    STOP,
    Availability,
    MockPolicy,
    OllamaPolicy,
    Resolution,
    ToolCall,
    UnrecognizedAction,
    coerce_action,
    resolve,
)


# ---------------------------------------------------------------- C-02 / I-004
def test_action_tag_union_members_construct():
    assert ToolCall(name="read_file", args={"path": "config.py"}).name == "read_file"
    assert ToolCall(name="read_file", args={"path": "config.py"}).args == {"path": "config.py"}
    assert STOP().final_outcome == "VERIFIED"  # default declared completion
    assert NOOP().note == ""


def test_coerce_action_passes_through_valid_actions():
    tc = ToolCall("search", {"query": "x"})
    assert coerce_action(tc) == tc
    assert coerce_action(STOP()) == STOP()
    assert coerce_action(NOOP("n")) == NOOP("n")


def test_coerce_action_rejects_garbage_as_error_not_silent_noop():
    # I-004/E-02: an unrecognizable output is an ERROR, never swallowed/NOOP'd
    for bad in (None, 42, "read_file", object(), "ToolCall"):
        with pytest.raises(UnrecognizedAction):
            coerce_action(bad)


# ---------------------------------------------------------------- MockPolicy
def test_mock_policy_returns_scripted_batches_in_order():
    script = [[ToolCall("read_file", {"path": "a"})], [STOP("VERIFIED")]]
    p = MockPolicy(script)
    first = p.select(None, None)
    assert first == [ToolCall("read_file", {"path": "a"})]
    second = p.select(None, None)
    assert second == [STOP("VERIFIED")]


def test_mock_policy_exhausted_returns_noop_not_false_verified():
    # I-006: only the verifier may settle VERIFIED; an exhausted script stalls
    p = MockPolicy([[]])  # one empty batch, then exhausted
    assert p.select(None, None) == []
    assert p.select(None, None) == [NOOP()]


def test_mock_policy_select_all_replays_deterministically():
    # R-13/I-002: two scripted policies replay the same batch sequence
    script = [[ToolCall("edit_file", {"path": "c.py", "op": "replace", "new": "x"})]]
    a = [list(b) for b in MockPolicy(script).select_all()]
    b = [list(b) for b in MockPolicy(script).select_all()]
    assert a == b


# ---------------------------------------------------------------- R-14 / E-11-E-12
def _probe(kind):
    # stand-in for a real (httpx) availability probe; injectable, no network
    def probe() -> tuple[bool, bool]:
        if kind == "down":
            return (False, False)
        if kind == "no_model":
            return (True, False)
        return (True, True)  # "up"

    return probe


def test_resolve_degraded_mock_when_daemon_down():
    r = resolve(_probe("down"), model="qwen3.8")
    assert isinstance(r, Resolution)
    assert r.availability is Availability.DEGRADED_MOCK
    assert r.exit_code == 0
    assert r.banner is not None and "DEGRADED_MOCK" in r.banner
    assert isinstance(r.policy, MockPolicy)  # degraded to the offline double


def test_resolve_pull_required_when_model_absent():
    r = resolve(_probe("no_model"), model="qwen3.8")
    assert r.availability is Availability.PULL_REQUIRED
    assert r.exit_code == 4
    assert "qwen3.8" in (r.remediation or "")


def test_resolve_run_real_when_model_present():
    r = resolve(_probe("up"), model="qwen3.8")
    assert r.availability is Availability.RUN_REAL
    assert r.exit_code == 0
    assert r.banner is None
    assert isinstance(r.policy, OllamaPolicy)  # only RUN_REAL selects the real policy


# ---------------------------------------------------------------- K-06 / T-02
def test_importing_policy_does_not_import_a_network_client():
    # K-06/T-02: `import policy` opens no socket; the Ollama client is lazy
    assert "httpx" not in sys.modules, "policy import must not pull in httpx"


def test_ollama_policy_construction_is_lazy():
    # OllamaPolicy is buildable without the (optional) real client present
    from coding_agent.policy import OllamaPolicy as OP

    p = OP(model="qwen3.8")
    assert isinstance(p, OP)
    assert "httpx" not in sys.modules  # construction alone must not import it
