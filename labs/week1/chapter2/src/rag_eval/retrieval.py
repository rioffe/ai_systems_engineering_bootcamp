r"""C-02 retrieval -- a deterministic, pure-Python BM25 retriever (R-02, R-17).

This module is the first stage of the pipeline and part of the **deterministic
boundary**: it uses only the stdlib (``collections``, ``math``, ``re``) plus the
shared ``types``. It names no LLM/Ollama/httpx/model (I-009 / T-02, pinned by a source
scan). Everything here -- the tokenizer, the idf/tf-idf formula, and the tie-break -- is
fixed so that a fixed corpus + query + (k1,b,tokenizer) yields a byte-identical ranked
list across runs (I-002 / T-04). The only probabilistic role downstream is the LLM;
retrieval never touches it.

BM25 (O-1): score(q,d) = sum over t in q of idf(t) * tf(t,d)*(k1+1) /
(tf + k1*(1 - b + b*|d|/avgdl)), with idf(t) = ln(1 + (N - n(t) + 0.5)/(n(t)+0.5)).
Tokenizer (O-1a): lower-case; split on `[^\w']+`; drop pure-numeric tokens unless
keep_numbers; optional stop-word filter; dict order is deterministic.
Ties (O-1b): equal scores resolve by doc_id ascending, so runs are byte-reproducible.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from .types import Document, ScoredDoc

# O-1a tokenizer split: any run that is NOT a word char or apostrophe.
_TOKEN_SPLIT = re.compile(r"[^\w']+")
# A token that is purely digits (dropped unless keep_numbers).
_NUMERIC = re.compile(r"^\d+$")

# A small, conventional stop-word list. None by default (the CLI / callers opt in);
# a deterministic frozenset so behaviour is reproducible (I-002).
DEFAULT_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "if",
        "then",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
        "from",
        "that",
        "this",
        "is",
        "are",
        "was",
        "were",
        "be",
        "by",
        "as",
        "at",
        "it",
    }
)


def tokenize(
    text: str,
    *,
    stop_words: frozenset[str] | None = None,
    keep_numbers: bool = True,
) -> list[str]:
    """O-1a tokenizer: lower-case, split, drop numeric, filter stops.

    Returns tokens in document order. Dict/Counter order is derived from this list, so
    there is no hash-seed dependence (I-002).
    """
    tokens: list[str] = []
    for raw in _TOKEN_SPLIT.split(text.lower()):
        tok = raw.strip("'")
        if tok == "":
            continue
        if _NUMERIC.match(tok) and not keep_numbers:
            continue
        if stop_words is not None and tok in stop_words:
            continue
        tokens.append(tok)
    return tokens


class BM25Retriever:
    """Rank a corpus for a query with the O-1 BM25 formula (C-02).

    Construct once for a corpus, then call `search(query, k)` many times. The index is
    precomputed at construction, so repeated queries are O(|query| x |hits|).
    """

    def __init__(
        self,
        documents: list[Document],
        *,
        k1: float = 1.5,
        b: float = 0.75,
        stop_words: frozenset[str] | None = None,
        keep_numbers: bool = True,
    ) -> None:
        self.documents: list[Document] = list(documents)
        self.k1 = k1
        self.b = b
        self.stop_words = stop_words
        self.keep_numbers = keep_numbers

        # Precompute per-document token counts + lengths, then the corpus-wide idf.
        self._doc_token_counts: list[dict[str, int]] = []
        self._doc_lengths: list[int] = []
        doc_freq: Counter[str] = Counter()
        for doc in self.documents:
            tfs = Counter(
                tokenize(
                    doc.text,
                    stop_words=self.stop_words,
                    keep_numbers=self.keep_numbers,
                )
            )
            self._doc_token_counts.append(tfs)
            self._doc_lengths.append(len(tfs))
            doc_freq.update(tfs.keys())
        self._n_docs = len(self.documents)
        self._doc_freq = doc_freq
        self._avgdl = (sum(self._doc_lengths) / self._n_docs) if self._n_docs else 0.0

    def _idf(self, term: str) -> float:
        n_t = self._doc_freq.get(term, 0)
        # O-1: ln(1 + (N - n(t) + 0.5)/(n(t) + 0.5)); N=0 => ln(1) = 0.
        if self._n_docs == 0:
            return 0.0
        return math.log(1.0 + (self._n_docs - n_t + 0.5) / (n_t + 0.5))

    def _score_document(self, query_terms: frozenset[str], i: int) -> float:
        tfs = self._doc_token_counts[i]
        dl = self._doc_lengths[i]
        ratio = dl / self._avgdl if self._avgdl else 0.0
        score = 0.0
        for t in query_terms:
            tf = tfs.get(t, 0)
            if tf == 0:
                continue
            denom = tf + self.k1 * (1.0 - self.b + self.b * ratio)
            idf = self._idf(t)
            if idf == 0.0:
                continue
            score += idf * (tf * (self.k1 + 1.0)) / denom
        return score

    def search(self, query: str, k: int) -> list[ScoredDoc]:
        """Rank the corpus for `query`, returning up to `k` ScoredDocs (score desc).

        Deterministic (I-002 / T-04): equal scores resolve by doc_id ascending (O-1b).
        Empty corpus or zero matches returns [] (E-02). Non-positive `k` returns [].
        """
        if k <= 0 or not self.documents:
            return []
        query_terms = frozenset(
            tokenize(query, stop_words=self.stop_words, keep_numbers=self.keep_numbers)
        )
        if not query_terms:
            return []

        scored: list[ScoredDoc] = []
        for i, doc in enumerate(self.documents):
            score = self._score_document(query_terms, i)
            if score > 0.0:
                scored.append(ScoredDoc(doc=doc, score=score, rank=1))

        # O-1b tie-break: score desc, then doc_id asc. Sort the full list (not just
        # top-k) so rank assignment is stable and reproducible independent of k.
        scored.sort(key=lambda sd: (-sd.score, str(sd.doc.doc_id)))
        for rank, sd in enumerate(scored, start=1):
            sd.rank = rank
        return scored[:k]


__all__ = ["BM25Retriever", "DEFAULT_STOP_WORDS", "tokenize"]
