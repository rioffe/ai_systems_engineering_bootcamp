"""C-04 the permission decision + the permission layer, enforced OUTSIDE the model.

The agent's security thesis made mechanical (section 11 / 18.10, I-008):
authorize gates EVERY tool call *before* it executes -- the policy may only
*request* an action; only the permission layer *permits* it. Precedence (C-04),
first DENY wins:

     1. path-in-sandbox     -> PATH_OUTSIDE_SANDBOX  (dynamic, I-003)
     2. run_shell command   -> COMMAND_FORBIDDEN     (dynamic prefix allow)
     3. tool in allow_list  -> NOT_IN_ALLOWLIST      (static, 11.1)
     4. MAY rule override   -> RULE_DENIED           (policy-based, 11.3)

A DENY carries a detail (I-008 records it on that iteration); a single DENY does
not terminate -- it routes to the next REASON (see control_loop, K-08). The same
path check also runs in tools.py (I-003 defense in depth).
"""

from __future__ import annotations

import os
import shlex
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .policy import ToolCall

ALLOWED = "ALLOWED"
NOT_IN_ALLOWLIST = "NOT_IN_ALLOWLIST"
PATH_OUTSIDE_SANDBOX = "PATH_OUTSIDE_SANDBOX"
COMMAND_FORBIDDEN = "COMMAND_FORBIDDEN"
RULE_DENIED = "RULE_DENIED"

# C-03 / static allow-list (11.1): the closed tool set the agent may use.
DEFAULT_ALLOWLIST = frozenset(
    {
        "list_files",
        "read_file",
        "search",
        "edit_file",
        "run_shell",
    }
)
# Dynamic prefix allow for run_shell (11.2): only verification / exec tools.
DEFAULT_COMMAND_PREFIXES = (
    "python",
    "python3",
    "pytest",
    "ruff",
    "mypy",
    "bash",
    "sh",
    "zsh",
    "make",
    "/bin/sh",
    "/bin/bash",
)


# C-04: the ALLOW/DENY authorization decision for one tool call.
@dataclass(frozen=True)
class Decision:
    allows: bool
    tool: str
    args: dict
    reason: str
    detail: str | None = None


# C-04 / section 11: the explicitly declared permission policy.
@dataclass(frozen=True)
class PermsConfig:
    sandbox_root: str
    allow_list: frozenset[str] = field(default_factory=lambda: DEFAULT_ALLOWLIST)
    allowed_command_prefixes: tuple[str, ...] = field(
        default_factory=lambda: DEFAULT_COMMAND_PREFIXES,
    )
    # MAY rule override (11.3): return a DENY Decision to block an action.
    rule: Callable[[ToolCall, PermsConfig], Decision | None] | None = field(default=None)


def _in_sandbox(raw_path: str, sandbox_root: str) -> bool:
    # ../, absolute, symlinks and $VAR all canonicalize via resolve() (I-003).
    root = Path(sandbox_root).resolve()
    target = (root / os.path.expandvars(raw_path)).resolve()
    return target == root or root in target.parents


def _prefix_ok(first: str, prefixes: tuple[str, ...]) -> bool:
    # A command prefix is allowed iff it equals or starts with one of the
    # allowed verification/exec prefixes (11.2); a plain loop avoids the
    # generator-expression-with-`or` parenthesization footgun.
    for p in prefixes:
        if first == p or first.startswith(p):
            return True
    return False


def authorize(
    tool_call: ToolCall,
    pconfig: PermsConfig,
    sandbox_root: str | None = None,
) -> Decision:
    # Fixed precedence, first DENY wins (C-04); sandbox_root may override per-call.
    root = sandbox_root or pconfig.sandbox_root
    name = tool_call.name
    args = tool_call.args

    # (1) path-in-sandbox -- any path/cwd arg must resolve inside the root.
    for key in ("path", "cwd"):
        value = args.get(key)
        if isinstance(value, str) and not _in_sandbox(value, root):
            return Decision(
                allows=False,
                tool=name,
                args=args,
                reason=PATH_OUTSIDE_SANDBOX,
                detail=f"{key} {value!r} escapes the sandbox root",
            )

        # (2) run_shell command-prefix allow.
    if name == "run_shell":
        command = args.get("command", "")
        pieces = shlex.split(command)
        first = pieces[0] if pieces else ""
        if not _prefix_ok(first, pconfig.allowed_command_prefixes):
            return Decision(
                allows=False,
                tool=name,
                args=args,
                reason=COMMAND_FORBIDDEN,
                detail=f"command {command!r} is not under an allowed prefix",
            )

        # (3) tool in the static allow-list.
    if name not in pconfig.allow_list:
        return Decision(
            allows=False,
            tool=name,
            args=args,
            reason=NOT_IN_ALLOWLIST,
            detail=f"tool {name!r} is not in the allow-list",
        )

        # (4) MAY rule override (11.3): a policy rule may deny an allowed tool.
    if pconfig.rule is not None:
        verdict = pconfig.rule(tool_call, pconfig)
        if verdict is not None and not verdict.allows:
            return Decision(
                allows=False,
                tool=name,
                args=args,
                reason=RULE_DENIED,
                detail=verdict.detail or "policy rule denied the action",
            )

    return Decision(True, name, args, ALLOWED)


__all__ = [
    "ALLOWED",
    "COMMAND_FORBIDDEN",
    "NOT_IN_ALLOWLIST",
    "PATH_OUTSIDE_SANDBOX",
    "RULE_DENIED",
    "Decision",
    "PermsConfig",
    "authorize",
]
