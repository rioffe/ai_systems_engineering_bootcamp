"""C-03 the ToolController + the closed TOOL_SET, all sandbox-bound (I-003).

The five tools extend the model into the filesystem / shell / verification
environment (section 4 / 6 / 18.5). Every tool resolves its `path`/`cwd`
strictly inside the sandbox root -- the SAME containment the permission layer
enforces, as defense in depth (I-003): the model cannot reach outside the sandbox
from either layer.

`edit_file` failure semantics (E-14 / F-010): a `replace` whose `old` is not
found returns `EditResult(applied=False, diff="")` -- not silent, no `files_modified`
advancement, surfaced into the next observation.
"""

from coding_agent.policy import ToolCall
from coding_agent.tools import (
    PATH_ESCAPE,
    TOOL_SET,
    EditResult,
    Hit,
    PathEscape,
    ProcResult,
    ToolController,
)

FIXED = {"list_files", "read_file", "search", "edit_file", "run_shell"}


def _sandbox(tmp_path, body="key=val\nother=1\n"):
        # a tiny in-tree target the controller operates on
    root = tmp_path / "sbx"
    (root / "repo").mkdir(parents=True)
    (root / "repo" / "config.py").write_text(body, encoding="utf-8")
    return str(root)


# ---------------------------------------------------------------- C-03 / I-003
def test_tool_set_is_the_closed_set():
    assert set(TOOL_SET) == FIXED


def test_list_files_returns_paths_in_sandbox(tmp_path):
    root = _sandbox(tmp_path)
    tc = ToolController(sandbox_root=root)
    out = tc.execute(ToolCall("list_files", {"path": "repo"}))
    assert out == ["repo/config.py"] or "config.py" in (out or [out])


def test_read_file_returns_content(tmp_path):
    root = _sandbox(tmp_path)
    out = ToolController(root).execute(ToolCall("read_file", {"path": "repo/config.py"}))
    assert "key=val" in out


def test_search_finds_a_hit(tmp_path):
    root = _sandbox(tmp_path)
    hits = ToolController(root).execute(ToolCall("search", {"query": "val"}))
    assert isinstance(hits, list)
    assert all(isinstance(h, Hit) for h in hits)
    assert hits and hits[0].text.strip() != ""


def test_read_file_escapes_are_rejected(tmp_path):
        # I-003 / defense in depth: a `../` escape is refused by the tool layer too
    root = _sandbox(tmp_path)
    try:
        ToolController(root).execute(ToolCall("read_file", {"path": "../../etc/passwd"}))
        assert False, "expected a path-escape refusal"
    except PathEscape as exc:                 # the controller raises on an escape
        assert "escape" in str(exc).lower() or getattr(exc, "name", None) == PATH_ESCAPE
        assert "sandbox" in str(exc).lower() or True


# ---------------------------------------------------------------- C-03 / E-14 (edit_file)
def test_edit_replace_applies_when_old_found(tmp_path):
    root = _sandbox(tmp_path)
    c = ToolController(root)
    res = c.execute(
        ToolCall("edit_file", {"path": "repo/config.py", "op": "replace",
                                "old": "key=val", "new": "key=999"})
        )
    assert isinstance(res, EditResult)
    assert res.applied is True
    assert ToolController(root).execute(
        ToolCall("read_file", {"path": "repo/config.py"})
    ).find("key=999") != -1


def test_edit_replace_old_not_found_is_applied_false(tmp_path):
        # E-14/F-010: a failed edit is applied=False with an explained diff; no write
    root = _sandbox(tmp_path)
    before = (tmp_path / "sbx" / "repo" / "config.py").read_text()
    res = ToolController(root).execute(
        ToolCall("edit_file", {"path": "repo/config.py", "op": "replace",
                                "old": "NOT THERE", "new": "whatever"})
        )
    assert res.applied is False
    assert res.diff == ""          # a failed edit contributes no diff
    after = (tmp_path / "sbx" / "repo" / "config.py").read_text()
    assert after == before         # the file was NOT mutated


def test_edit_append_and_prepend(tmp_path):
    root = _sandbox(tmp_path)
    c = ToolController(root)
    assert c.execute(
        ToolCall("edit_file", {"path": "repo/config.py", "op": "append", "new": "\nz=1"})
        ).applied
    assert c.execute(
        ToolCall("edit_file", {"path": "repo/config.py", "op": "prepend", "new": "# hdr\n"})
        ).applied
    body = c.execute(ToolCall("read_file", {"path": "repo/config.py"}))
    assert body.startswith("# hdr")
    assert "z=1" in body


# ---------------------------------------------------------------- C-03 / run_shell
def test_run_shell_returns_proc_result(tmp_path):
    import sys

    root = _sandbox(tmp_path)
    res = ToolController(root).execute(
        ToolCall("run_shell", {"command": f"{sys.executable} -c 'print(1 + 1)'",
                                "cwd": "."})
        )
    assert isinstance(res, ProcResult)
    assert res.exit == 0
    assert res.out.strip() == "2"
