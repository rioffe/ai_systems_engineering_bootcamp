# pyright: reportMissingImports=false
from pathlib import Path

import pytest

from research_agent.tools import PermanentError, build_registry

ROOT = Path(__file__).parents[1]


def test_search_is_ranked_and_retrieve_has_provenance():
    registry = build_registry(ROOT / "corpus")
    hits = registry.search("reimbursement limit")
    assert hits[0]["doc_id"] == "policy-primary"
    document = registry.retrieve("policy-primary")
    assert document["quality"] == "primary"


def test_unknown_document_is_permanent():
    with pytest.raises(PermanentError):
        build_registry(ROOT / "corpus").retrieve("missing")


def test_delete_is_registered_but_denied():
    assert build_registry(ROOT / "corpus").specs["delete_file"].permission == "deny"
