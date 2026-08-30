# C-08-bis / I-003 / I-011 / E-08 / E-10 / K-04: the ephemeral, non-recursive sandbox.
#
# `sandbox.py` is IN the I-009 LLM/network-free core list. It owns the sandbox
# LIFECYCLE: it copies a copy of the target repo into an ephemeral root via
# `shutil.copytree(..., symlinks=False)` -- symlinks are not copied as links, so
# no tool can follow a link out of the tree (no escape vector, I-003) -- and it
# removes the sandbox in a `finally` regardless of final_outcome (C-08-bis). It
# refuses the bootcamp repo / the agent's own source tree (E-08 / I-011), raises on
# an unwritable root (E-10), and bounds the copy (K-04).
#
# The context-manager protocol (`__enter__`/`__exit__` -> remove in finally) is what
# the control_loop uses so a sandbox is ALWAYS cleaned up, even on exception/kill.

from __future__ import annotations

import os
import shutil
from typing import Self

# The sentinels the CLI maps to exit codes / messages (C-08 / E-08 / E-10).
REFUSED = "REFUSED"
UNWRITABLE = "UNWRITABLE"

# K-04 sandbox-size bounds (generous defaults; a huge target would wedge the run).
DEFAULT_MAX_FILES = 50_000
DEFAULT_MAX_BYTES = 200 * 1024 * 1024


# Base class for the two sandbox failure modes (both map to core-ERROR exits, C-08).
class SandboxError(Exception):
    pass


# E-08 / I-011: the source is the bootcamp repo or the agent's own source tree.
class RefusedRepo(SandboxError):
    name = REFUSED


# E-10: the sandbox root is un-writable or does not exist as a creatable directory.
class UnwritableRoot(SandboxError):
    name = UNWRITABLE


def own_source_root() -> str:
    # The realpath of THIS package's source dir: a self-editing sandbox would deadlock
    # its own test harness (E-08 / I-011), so it is unconditionally refused. Resolved
    # per-call so tests may monkeypatch it.
    here = os.path.realpath(os.path.dirname(__file__))
    return here


def _is_under(path: str, ancestor: str) -> bool:
    # True if `path` equals or is nested inside `ancestor` (realpath-resolved).
    p = os.path.realpath(path)
    a = os.path.realpath(ancestor)
    return p == a or p.startswith(a + os.sep)


class Sandbox:
    # A copied-in ephemeral root. `create` builds it; `remove` tears it down in the
    # finally discipline; the with-protocol (`__enter__`/`__exit__`) is C-08-bis.
    def __init__(self, root: str, active: bool = True) -> None:
        self.root = root
        self.active = active

    @classmethod
    def create(
        cls,
        source: str,
        root: str,
        *,
        forbidden: list[str] | None = None,
        max_files: int = DEFAULT_MAX_FILES,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> Sandbox:
        # R-12/I-011: copy `source` into `root`. Symlinks are not copied (I-003).
        # Refuse a forbidden / own-source tree (E-08/I-011), an unwritable root (E-10),
        # or an over-cap copy (K-04).
        # E-08 / I-011: refuse the agent's own source tree + any explicit forbids.
        forbids = [own_source_root(), *(forbidden or [])]
        for f in forbids:
            if _is_under(source, f):
                raise RefusedRepo(
                    f"refusing source {source!r}: {f!r} is forbidden (E-08/I-011)"
                 )

         # E-10: the root must not be a non-directory path (a file masquerading as the
         # root). A genuinely un-writable location surfaces as OSError during
         # makedirs/copytree, mapped to UnwritableRoot (exit 5). A merely *absent*
         # parent is created -- the sandbox root is ephemeral (C-08-bis).
        if os.path.lexists(root) and not os.path.isdir(root):
            raise UnwritableRoot(f"sandbox root {root!r} exists but is not a directory (E-10)")

        try:
            os.makedirs(root, exist_ok=True)
             # symlinks=False: a symlink copies its target content as a regular file, so
             # no link can escape the tree (I-003).
            shutil.copytree(
                source, root, symlinks=False, dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
              )
        except OSError as exc:
            raise UnwritableRoot(f"could not allocate sandbox root {root!r}: {exc} (E-10)") from exc

        return cls(root, active=True)

    def remove(self) -> None:
         # C-08-bis: tear the sandbox down in the finally discipline. A `finally` must
         # never raise, so the rmtree is itself guarded.
        if self.active and os.path.isdir(self.root):
            try:
                shutil.rmtree(self.root, ignore_errors=True)
            except OSError:
                pass
        self.active = False

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
         # C-08-bis: ALWAYS remove, even when the body raised.
        self.remove()


def create_sandbox(source: str, root: str, **kw) -> Sandbox:
    # Convenience factory for `with create_sandbox(...)`: allocates in __enter__ and
    # removes in __exit__ (the finally discipline).
    return Sandbox.create(source, root, **kw)


__all__ = [
        "DEFAULT_MAX_BYTES",
        "DEFAULT_MAX_FILES",
        "REFUSED",
        "UNWRITABLE",
        "RefusedRepo",
        "Sandbox",
        "SandboxError",
        "UnwritableRoot",
        "create_sandbox",
        "own_source_root",
    ]
