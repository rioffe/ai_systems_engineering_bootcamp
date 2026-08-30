# The C-09 verifier target (SPEC section 9): the agent runs `pytest -q` against
# exactly this file to close its loop. `conftest.py` (next to this dir) puts
# `repo/` on sys.path so `import config` resolves regardless of cwd.
from config import parse_config  # type: ignore


def test_parse_basic():
    assert parse_config("a=1\nb=2") == {"a": "1", "b": "2"}


def test_ignores_blank_lines():
    assert parse_config("a=1\n\nb=2") == {"a": "1", "b": "2"}
