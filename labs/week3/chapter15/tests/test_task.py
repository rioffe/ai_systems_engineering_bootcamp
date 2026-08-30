"""C-01 the Task input (SPEC section 4 / C-01, R-01).

A `Task` is the input to one closed-loop run: a natural-language prompt, the
target repository to copy into the sandbox, and the `VerifySpec` that closes the
loop (C-05). `success_token` / `acceptance_test` are MAY sub-criteria.
"""

import dataclasses

import pytest

from coding_agent.task import Task
from coding_agent.verifier import VerifySpec

V = VerifySpec(kind="tests", command="pytest -q")


def test_task_carries_the_c01_fields():
    t = Task(
        task_id="parse-config",
        prompt="parse key=value lines",
        target_repo="fixtures/parse-config/repo",
        verifier=V,
     )
    assert t.task_id == "parse-config"
    assert t.prompt.startswith("parse")
    assert t.target_repo == "fixtures/parse-config/repo"
    assert t.verifier.kind == "tests"


def test_task_optional_fields_default_none():
    t = Task(task_id="t", prompt="p", target_repo="repo", verifier=V)
    assert t.success_token is None
    assert t.acceptance_test is None


def test_task_accepts_optional_subcriteria():
    t = Task(
        task_id="t",
        prompt="p",
        target_repo="repo",
        verifier=V,
        success_token="delimiter not in",
        acceptance_test="test_parse_basic",
     )
    assert t.success_token == "delimiter not in"
    assert t.acceptance_test == "test_parse_basic"


def test_task_is_immutable():
       # frozen dataclass: an attribute rebind raises FrozenInstanceError
    t = Task(task_id="t", prompt="p", target_repo="repo", verifier=V)
    with pytest.raises(dataclasses.FrozenInstanceError):
        t.prompt = "mutated!"


@pytest.mark.parametrize(
   "bad",
   [
        {"task_id": "", "prompt": "p", "target_repo": "r", "verifier": V},
        {"task_id": "t", "prompt": "", "target_repo": "r", "verifier": V},
        {"task_id": "t", "prompt": "p", "target_repo": "", "verifier": V},
    ],
)
def test_task_rejects_empty_required_fields(bad):
      # an empty required field is a construction error (before the loop, cf. E-01)
    with pytest.raises(ValueError):
        Task(**bad)
