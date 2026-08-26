"""Shared fixtures + offline posture for the chapter2 SPEC §9 suite.

The suite must run **fully offline** with no Ollama daemon and no network
(K-01/T-14). The only model-dependent behaviour in the system is the LLM + judge,
which these core tests never touch -- they drive the deterministic modules and the
deterministic structured gate only.
"""

import os

# GUI parity with chapter1: headless Qt if any GUI test is ever added (T-16).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from rag_eval.corpus import generate_corpus_and_questions
from rag_eval.retrieval import BM25Retriever


@pytest.fixture(scope="session")
def corpus(tmp_path_factory):
 """A generated (100-doc / 25-question) corpus + its BM25 retriever, shared by tier.

 Seeded (seed=42) so the corpus and its ranking are deterministic across the run
  (R-15/I-002). Returns ``(docs, info, questions, retriever)``.
 """
 directory = str(tmp_path_factory.mktemp("corpus"))
 docs, info, questions = generate_corpus_and_questions(directory, seed=42)
 retriever = BM25Retriever(docs)
 return docs, info, questions, retriever
