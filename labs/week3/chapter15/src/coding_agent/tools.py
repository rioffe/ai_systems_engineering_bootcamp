# C-03 the ToolController + the closed TOOL_SET, all sandbox-bound (I-003).
#
# The five tools extend the model into the filesystem / shell / verification
# environment (section 4 / 6 / 18.5). Every tool resolves its `path`/`cwd` strictly
# inside the sandbox root -- the SAME containment the permission layer enforces, as
# defense in depth (I-003): the model cannot reach outside the sandbox from either
# layer.
#
# edit_file failure semantics (E-14 / F-010): a `replace` whose `old` is not found
# returns EditResult(applied=False, diff="") -- not silent, no files_modified
# advancement, surfaced into the next observation.

from __future__ import annotations

import os
import re
import shlex
import subprocess
from dataclasses import dataclass

from .permissions import DEFAULT_COMMAND_PREFIXES, _in_sandbox, _prefix_ok
from .policy import ToolCall

# C-03: the closed tool schema (name -> {in, out}). This IS the closed space I-004 /
# R-04 gate on -- any tool name outside this set is an unknown tool (coerced ERROR).
TOOL_SET = {
    "list_files": {"in": {"path": "str", "glob": "str?"}, "out": "list[str]"},
    "read_file": {"in": {"path": "str"}, "out": "str"},
    "search": {"in": {"query": "str", "path_glob": "str?"}, "out": "list[Hit]"},
    "edit_file": {
        "in": {
            "path": "str",
            "op": "enum[replace|append|prepend]",
            "old": "str?",
            "new": "str",
        },
        "out": "EditResult{applied: bool, diff: str}",
    },
    "run_shell": {
        "in": {"command": "str", "cwd": "str?"},
        "out": "ProcResult{exit: int, out: str, err: str}",
    },
}
# The closed edit operations (C-03 edit_file op).
EDIT_OPS = {"replace", "append", "prepend"}
PATH_ESCAPE = "PathEscape"


# C-03 edit_file output. applied=False means the edit did NOT write (E-14).
@dataclass(frozen=True)
class EditResult:
    applied: bool
    diff: str
    detail: str = ""


# C-03 search: a grep-like match (path, 1-based line, the matching text).
@dataclass(frozen=True)
class Hit:
    path: str
    line: int
    text: str


# C-03 run_shell: the bounded exit/out/err the verifier and policy read.
@dataclass(frozen=True)
class ProcResult:
    exit: int
    out: str
    err: str = ""


# I-003: a path/cwd that would resolve outside the sandbox root.
class PathEscape(Exception):
    name = PATH_ESCAPE

    def __init__(self, raw: str, root: str) -> None:
        self.raw = raw
        self.root = root
        super().__init__(f"path escapes the sandbox: {raw!r} is outside {root!r}")


# Dispatch a ToolCall inside a single sandbox root. Path containment is enforced HERE
# too (defense in depth with the permission layer, I-003).
class ToolController:
    def __init__(self, sandbox_root: str, max_output: int = 8000) -> None:
        self.root = sandbox_root
        self.max_output = max_output

    def _resolve(self, raw: str) -> str:
        # Resolve `raw` inside the sandbox; raise PathEscape on any escape (../,
        # absolute, symlink, $VAR) -- I-003.
        if not _in_sandbox(raw, self.root):
            raise PathEscape(raw, self.root)
        return os.path.join(self.root, raw)

    def execute(self, call: ToolCall) -> object:
        # Dispatch by name over the closed TOOL_SET (I-004). A tool name outside the
        # set is an unknown tool -- the loop coerces it to an ERROR (E-02).
        handler = getattr(self, "_t_" + call.name, None)
        if handler is None:
            raise KeyError(f"unknown tool {call.name!r} (not in TOOL_SET)")
        return handler(call.args)

    def _t_list_files(self, args: dict) -> list[str]:
        # List files under `path` (default "."), relative posix paths. `list_files`
        # DISCOVERS files but, per C-06, does NOT increment files_read.
        path = self._resolve(args.get("path", "."))
        matches: list[str] = []
        for dirpath, _dirs, files in os.walk(path):
            for file in sorted(files):
                full = os.path.join(dirpath, file)
                rel = os.path.relpath(full, self.root).replace(os.sep, "/")
                matches.append(rel)
        matches.sort()
        return matches

    def _t_read_file(self, args: dict) -> str:
        # `read_file` OPENS a path (counts toward files_read, C-06).
        target = self._resolve(args["path"])
        with open(target, "r", encoding="utf-8") as fh:
            return fh.read()

    def _t_search(self, args: dict) -> list[Hit]:
        # A grep-like, case-sensitive substring search over the sandbox tree.
        # `search` DISCOVERS matches but does NOT increment files_read (C-06).
        pattern = re.compile(re.escape(args["query"]))
        hits: list[Hit] = []
        for dirpath, _dirs, files in os.walk(self.root):
            for file in sorted(files):
                if file.startswith("."):
                    continue
                full = os.path.join(dirpath, file)
                rel = os.path.relpath(full, self.root).replace(os.sep, "/")
                try:
                    with open(full, "r", encoding="utf-8", errors="replace") as fh:
                        for i, line in enumerate(fh, start=1):
                            if pattern.search(line):
                                hits.append(Hit(path=rel, line=i, text=line.rstrip("\n")))
                except OSError:
                    continue
        return hits

    def _t_edit_file(self, args: dict) -> EditResult:
        # The ONLY mutation tool. op in {replace, append, prepend}. Applied only when
        # the write actually lands; otherwise applied=False with a reason and an
        # empty diff (E-14 / F-010) so a failed edit never counts as a modification.
        target = self._resolve(args["path"])
        op = args.get("op", "replace")
        new = args.get("new", "")
        if op not in EDIT_OPS:
            return EditResult(False, "", f"unknown edit op {op!r}")
        with open(target, "r", encoding="utf-8") as fh:
            original = fh.read()

        if op == "replace":
            old = args.get("old", "")
            if old not in original:
                # E-14/F-010: a failed replace is surfaced, not silent.
                return EditResult(False, "", f"old not found: {old!r}")
            updated = original.replace(old, new, 1)
            diff = f"--- old\n{old}\n+++ new\n{new}"
        elif op == "append":
            updated = original + new
            diff = f"+++ append\n{new}"
        else:
            updated = new + original
            diff = f"+++ prepend\n{new}"

        if updated == original:
            return EditResult(False, "", "edit produced no change")
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(updated)
        return EditResult(True, diff)

    def _t_run_shell(self, args: dict) -> ProcResult:
        # run verification / exec commands (tests/typecheck/lint/build). Re-checks the
        # command prefix (defense in depth) and runs in a bounded subprocess (K-04).
        # This tool is itself permission-gated (R-05).
        command = args.get("command", "")
        if not command.strip():
            return ProcResult(exit=2, out="", err="run_shell: empty command")
        pieces = shlex.split(command)
        first = pieces[0] if pieces else ""
        base = os.path.basename(first)
        # match the allow-list against the executable AND its basename, so a full
        # path like /usr/bin/python3 is judged on `python3` (11.2 prefix allow).
        if not (
            _prefix_ok(first, DEFAULT_COMMAND_PREFIXES)
            or _prefix_ok(base, DEFAULT_COMMAND_PREFIXES)
        ):
            return ProcResult(exit=2, out="", err=f"run_shell: command {command!r} not allowed")
        run_cwd = self._resolve(args["cwd"]) if args.get("cwd") else self.root
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=run_cwd,
                capture_output=True,
                text=True,
                timeout=120.0,
                check=False,
            )
        except FileNotFoundError:
            return ProcResult(exit=127, out="", err=f"command not found: {command!r}")
        except subprocess.TimeoutExpired:
            return ProcResult(exit=124, out="", err=f"timeout: {command!r}")
        out = proc.stdout[-(self.max_output) :]
        err = proc.stderr[-(self.max_output) :]
        return ProcResult(exit=proc.returncode, out=out, err=err)


__all__ = [
    "EDIT_OPS",
    "PATH_ESCAPE",
    "TOOL_SET",
    "EditResult",
    "Hit",
    "PathEscape",
    "ProcResult",
    "ToolController",
]
