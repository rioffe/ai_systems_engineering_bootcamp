"""C-08-bis / I-003 / I-011 / E-08 / E-10: the ephemeral, non-recursive sandbox.

`sandbox.py` is an I-009 core module: an LLM/network-free owner of the sandbox
lifecycle. It copES a copy of the target repo into an ephemeral root via
`shutil.copytree(..., symlinks=False)` (symlinks are NOT copied -- no escape
vector, I-003) and removes it in a `finally` regardless of outcome (C-08-bis).
Refuses the bootcamp repo / the agent's own source tree (E-08 / I-011); raises on
an unwritable root (E-10).
"""
from pathlib import Path

from coding_agent.sandbox import (
    REFUSED,
    UNWRITABLE,
    RefusedRepo,
    Sandbox,
    SandboxError,
    UnwritableRoot,
    create_sandbox,
)


def test_create_copies_source_into_root(tmp_path):
        # R-12 / I-011: the target repo is copied in; edits land on the COPY.
    src = tmp_path / "src"
    (src).mkdir()
    (src / "config.py").write_text("X = 1\n", encoding="utf-8")
    root = tmp_path / "agent-sbx" / "t1"
    sb = Sandbox.create(src, root)
    try:
        assert (Path(root) / "config.py").read_text() == "X = 1\n"
        assert sb.active
    finally:
        sb.remove()


def test_remove_in_finally_deletes_root(tmp_path):
        # C-08-bis: the sandbox is removed regardless of outcome.
    src = tmp_path / "src"
    src.mkdir()
    root = tmp_path / "agent-sbx" / "t2"
    Sandbox.create(src, root)
    assert (root / "config.py").exists() or root.exists()
    # remove() must delete the sandbox even if it was "used".
    Sandbox(root, active=True).remove()
    assert not root.exists()


def test_create_via_context_manager_removes_on_success(tmp_path):
        # C-08-bis in a with-block -- removed in finally.
    src = tmp_path / "src"
    src.mkdir()
    (src / "f.txt").write_text("hi", encoding="utf-8")
    root = tmp_path / "agent-sbx" / "t3"
    with create_sandbox(src, root) as sb:
                assert (Path(root) / "f.txt").exists() and sb.active
    assert not root.exists()                    # the finally cleaned up


def test_create_refuses_forbidden_source(tmp_path):
        # E-08 / I-011: refuse the agent's own source tree / bootcamp repo.
    src = tmp_path / "forbidden_tree"
    src.mkdir()
    root = tmp_path / "agent-sbx" / "t4"
    try:
        Sandbox.create(src, root, forbidden=[str(src)])
        assert False, "expected a refusal"
    except RefusedRepo as exc:
        assert REFUSED in str(exc).lower() or "refus" in str(exc).lower()


def test_create_refuses_own_source_root(tmp_path, monkeypatch):
        # I-011 defense: the agent can never target its own package dir.
    src_dir = tmp_path / "coding_agent"
    src_dir.mkdir()
    monkeypatch.setattr("coding_agent.sandbox.own_source_root", lambda: str(src_dir))
    root = tmp_path / "agent-sbx" / "t5"
    try:
        Sandbox.create(src_dir, root)
        assert False, "expected the own-source root to be refused"
    except RefusedRepo:
        pass


def test_symlinks_are_not_copied(tmp_path):
        # I-003: symlinks are NOT copied (no escape vector).
    src = tmp_path / "src"
    src.mkdir()
    real = tmp_path / "outside_secret.txt"
    real.write_text("secret", encoding="utf-8")
    link = src / "link.txt"
    link.symlink_to(real)
    root = tmp_path / "agent-sbx" / "t6"
    Sandbox.create(src, root)
    try:
        copied = Path(root) / "link.txt"
        assert not copied.is_symlink()          # not copied AS a symlink
    finally:
        Sandbox(root, active=True).remove()


def test_unwritable_root_raises(tmp_path):
        # E-10: an unwritable / non-existent sandbox root -> SandboxError (exit 5).
    src = tmp_path / "src"
    src.mkdir()
    bad_root = tmp_path / "root-is-a-file"
    bad_root.write_text("i am a file", encoding="utf-8")
    try:
        Sandbox.create(src, bad_root)
        assert False, "expected an unwritable-root error"
    except UnwritableRoot as exc:
        assert UNWRITABLE in str(exc).lower() or "writ" in str(exc).lower() or "exist" in str(exc).lower()


def test_sandbox_error_is_base():
        assert issubclass(RefusedRepo, SandboxError)
        assert issubclass(UnwritableRoot, SandboxError)


if __name__ == "__main__":
     raise SystemExit("pytest tests/test_sandbox.py")
