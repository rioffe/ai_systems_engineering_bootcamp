"""Deterministic local-corpus tools."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ToolError(Exception):
    pass


class TransientError(ToolError):
    pass


class PermanentError(ToolError):
    pass


class RateLimitError(ToolError):
    pass


class AuthenticationError(ToolError):
    pass


@dataclass(frozen=True)
class SearchHit:
    doc_id: str
    title: str
    snippet: str
    quality: str
    published: str


@dataclass(frozen=True)
class Document:
    doc_id: str
    title: str
    text: str
    quality: str
    published: str
    conflict_marker: dict[str, Any] | None = None


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    failure_classes: list[str]
    permission: str


class ToolRegistry:
    def __init__(self, documents: list[Document], fault: Any = None):
        self.documents = {document.doc_id: document for document in documents}
        self.fault = fault
        self.specs = {
            "search": ToolSpec(
                "search",
                "Find documents",
                {"type": "object", "required": ["query"]},
                {"type": "array"},
                ["TRANSIENT"],
                "allow",
            ),
            "retrieve": ToolSpec(
                "retrieve",
                "Read a document",
                {"type": "object", "required": ["document_id"]},
                {"type": "object"},
                ["PERMANENT"],
                "allow",
            ),
            "delete_file": ToolSpec(
                "delete_file",
                "Delete a file",
                {"type": "object", "required": ["path"]},
                {"type": "object"},
                ["PERMISSION"],
                "deny",
            ),
        }

    def search(self, query: str) -> list[dict[str, Any]]:
        if not isinstance(query, str):
            raise TypeError("query must be a string")
        terms = set(query.lower().split())
        hits = []
        for document in self.documents.values():
            score = len(terms & set(document.text.lower().split()))
            if score:
                hits.append((score, document))
        return [
            {
                "doc_id": d.doc_id,
                "title": d.title,
                "snippet": d.text,
                "quality": d.quality,
                "published": d.published,
            }
            for _, d in sorted(hits, key=lambda pair: (-pair[0], pair[1].doc_id))
        ]

    def retrieve(self, document_id: str) -> dict[str, Any]:
        document = self.documents.get(document_id)
        if document is None:
            raise PermanentError(f"unknown document_id: {document_id}")
        return {
            "doc_id": document.doc_id,
            "title": document.title,
            "text": document.text,
            "quality": document.quality,
            "published": document.published,
            "conflict_marker": document.conflict_marker,
        }


def load_corpus(path: str | Path) -> list[Document]:
    documents = []
    try:
        for line in Path(path).read_text().splitlines():
            if line.strip():
                raw = json.loads(line)
                documents.append(
                    Document(
                        raw["doc_id"],
                        raw.get("title", raw["doc_id"]),
                        raw["text"],
                        raw["quality"],
                        raw["published"],
                        raw.get("conflict_marker"),
                    )
                )
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"corpus violation: {exc}") from exc
    if not documents:
        raise ValueError("corpus violation: empty corpus")
    return documents


def build_registry(corpus_dir: str | Path, fault: Any = None) -> ToolRegistry:
    path = Path(corpus_dir)
    files = sorted(path.glob("*.jsonl")) if path.is_dir() else [path]
    docs = []
    for file in files:
        docs.extend(load_corpus(file))
    return ToolRegistry(docs, fault)
