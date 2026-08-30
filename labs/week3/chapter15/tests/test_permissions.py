"""C-04 the permission decision + C-08 permission layer, enforced OUTSIDE the model.

`authorize` gates EVERY tool call *before* it executes (R-05 / I-008). It is the
chapter's security thesis made mechanical: the policy may only *request* an
action; only the permission layer *permits* it (§11 / §18.10). Evaluation
precedence (C-04): (1) path-in-sandbox, (2) `run_shell` command-prefix,
(3) tool in `allow_list`, (4) MAY rule -- first `DENY` wins.

The decision shape is `ALLOW` / `DENY` (C-04); a `DENY` carries one of
`NOT_IN_ALLOWLIST | PATH_OUTSIDE_SANDBOX | COMMAND_FORBIDDEN | RULE_DENIED` plus
a `detail` (I-008 records it on the iteration, I-003 defense-in-depth).
"""

from coding_agent.permissions import (
    ALLOWED,
    COMMAND_FORBIDDEN,
    NOT_IN_ALLOWLIST,
    PATH_OUTSIDE_SANDBOX,
    PermsConfig,
    authorize,
)
from coding_agent.policy import ToolCall

ROOT = "/tmp/agent-sbx-parse-config"

ALL_FIVE = {"list_files", "read_file", "search", "edit_file", "run_shell"}


# ---------------------------------------------------------------- C-03 / C-04
def test_default_config_allows_the_five_tools_in_sandbox():
    # T-03: default PermsConfig allows list_files/read_file/search/edit_file/run_shell
    cfg = PermsConfig(sandbox_root=ROOT)
    for name in ALL_FIVE:
        tc = ToolCall(
            name, {"path": "repo/config.py"} if name != "run_shell" else {"command": "pytest -q"}
        )
        decision = authorize(tc, cfg)
        assert decision.allows, f"default should ALLOW {name}"
        assert decision.reason == ALLOWED


def test_default_allowlist_is_the_closed_tool_set():
    cfg = PermsConfig(sandbox_root=ROOT)
    assert set(cfg.allow_list) == ALL_FIVE


# ---------------------------------------------------------------- I-003 / T-03
def test_authorize_denies_paths_outside_sandbox_escape():
    # T-03: the permission layer rejects an injected `../escape` tool call
    cfg = PermsConfig(sandbox_root=ROOT)
    for name in ("edit_file", "read_file", "run_shell"):
        tc = ToolCall(
            name, {"path": "../escape.txt", "command": "pytest -q", "op": "replace", "new": "x"}
        )
        decision = authorize(tc, cfg)
        assert not decision.allows, f"{name} must be DENIED for an escape"
        assert decision.reason == PATH_OUTSIDE_SANDBOX
        assert decision.detail


def test_authorize_denies_absolute_paths_outside_sandbox():
    cfg = PermsConfig(sandbox_root=ROOT)
    decision = authorize(ToolCall("read_file", {"path": "/etc/passwd"}), cfg)
    assert not decision.allows
    assert decision.reason == PATH_OUTSIDE_SANDBOX


def test_authorize_allows_paths_inside_sandbox():
    # a path that resolves strictly inside the root is ALLOWED
    cfg = PermsConfig(sandbox_root=ROOT)
    decision = authorize(ToolCall("read_file", {"path": "repo/config.py"}), cfg)
    assert decision.allows
    assert decision.reason == ALLOWED


# ---------------------------------------------------------------- C-04 / E-09
def test_authorize_denies_run_shell_forbidden_command_prefix():
    cfg = PermsConfig(sandbox_root=ROOT)
    decision = authorize(ToolCall("run_shell", {"command": "rm -rf /"}), cfg)
    assert not decision.allows
    assert decision.reason == COMMAND_FORBIDDEN


def test_authorize_allows_run_shell_allowed_prefix():
    cfg = PermsConfig(sandbox_root=ROOT)
    decision = authorize(ToolCall("run_shell", {"command": "pytest -q"}), cfg)
    assert decision.allows


def test_authorize_denies_tool_not_in_allowlist():
    # E-09: a tool outside the static allow-list is NOT_IN_ALLOWLIST
    cfg = PermsConfig(sandbox_root=ROOT, allow_list=frozenset({"read_file"}))
    decision = authorize(ToolCall("run_shell", {"command": "pytest -q"}), cfg)
    assert not decision.allows
    assert decision.reason == NOT_IN_ALLOWLIST


# ---------------------------------------------------------------- C-04 (MAY rule)
def test_authorize_rule_may_override_to_deny():
    # a rule (policy-based, section 11.3) can override an otherwise-allowed tool
    def rule(tc, ctx):
        from coding_agent.permissions import Decision

        if tc.args.get("path") == "secret.py":
            return Decision(
                allows=False,
                tool=tc.name,
                args=tc.args,
                reason="RULE_DENIED",
                detail="rule blocks secret.py",
            )
        return None

    cfg = PermsConfig(sandbox_root=ROOT, rule=rule)
    decision = authorize(
        ToolCall("edit_file", {"path": "secret.py", "op": "replace", "new": "x"}),
        cfg,
    )
    assert not decision.allows
    assert decision.reason == "RULE_DENIED"


def test_decision_allow_shape_carry_reason_and_args():
    # C-04: ALLOW carries {tool, args, reason: ALLOWED}
    cfg = PermsConfig(sandbox_root=ROOT)
    tc = ToolCall("list_files", {"path": "."})
    decision = authorize(tc, cfg)
    assert decision.allows
    assert decision.tool == "list_files"
    assert decision.args == {"path": "."}
    assert decision.reason == ALLOWED
