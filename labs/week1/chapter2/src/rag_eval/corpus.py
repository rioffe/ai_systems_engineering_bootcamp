"""C-01 corpus + ground-truth (R-10/R-14/R-15, §15/§17).

Three responsibilities, all **deterministic** and stdlib-only (part of the deterministic
boundary; names no LLM/network -- I-009/T-02):

* ``load_corpus(path, ...)`` loads the ~100-doc corpus from either a directory of
   ``documents/NNN.txt`` (doc_id = the filename stem) or a single ``.jsonl`` / ``.json``.
    A malformed entry raises at *load time* with the offending path unless ``strict=False``
      (E-01): we never silently index a partial corpus.
* ``load_questions(path, corpus, ...)`` loads the **grounded** question dataset
   (question + gold_answer + relevant_docs + tier, §15) and enforces ground-truth integrity
      (I-013/E-15/T-15): every ``relevant_docs`` id must exist in the corpus, so a bad
        dataset fails fast instead of silently zeroing recall.
* ``generate_corpus`` / ``generate_corpus_and_questions`` author a fresh corpus **and** its
    ground-truth question set deterministically for a fixed seed, so the eval has a stable
        baseline (R-15, T-01). The question <-> relevant-docs mapping is fixed at generation
          time across the four §17 tiers.
"""

from __future__ import annotations

import json
import os
import random
import re
from typing import Any

from .types import Document, Question


# A corpus/question artifact that is unusable. The offending path/message is carried so the
# CLI can surface it with exit code 3 (§5.1 / E-01 / E-15 / T-15).
class CorpusError(ValueError):
    pass


# ------------------------------------------------------------------- corpus loading
def load_corpus(
    path: str | None = None,
    *,
    strict: bool = True,
    jsonl: str | None = None,
    docs_dir: str | None = None,
    keep_numbers: bool = True,
) -> list[Document]:
    """Load the ~100-doc corpus (C-01). Returns the loaded ``Document`` list.

    `path` (or `docs_dir`) that is a **directory** loads ``documents/NNN.txt`` (or every
    ``*.txt``) with ``doc_id = filename stem``. `path`/`jsonl` that is a ``.jsonl`` or
    ``.json`` document file loads line(s) of ``{doc_id, text, domain?}``. A malformed entry
    raises ``CorpusError`` (E-01) with the offending path unless ``strict=False`` (skip).
    """
    target = jsonl or path or docs_dir
    if target is None:
        target = "documents"

    if os.path.isdir(target):
        return _load_txt_dir(target, strict=strict)

    if target.endswith(".jsonl"):
        return _load_jsonl(target, strict=strict)
    if target.endswith(".json"):
        return _load_json(target, strict=strict)

    raise CorpusError(f"not a corpus path (dir or .jsonl/.json): {target!r}")


def _load_txt_dir(directory: str, *, strict: bool = True) -> list[Document]:
    files = sorted(
        f for f in os.listdir(directory) if f.endswith(".txt") and not f.startswith(".")
    )
    if not files:
        raise CorpusError(f"no .txt documents found in {directory!r}")
    docs: list[Document] = []
    for name in files:
        full = os.path.join(directory, name)
        try:
            with open(full, encoding="utf-8") as handle:
                text = handle.read()
        except OSError as exc:  # unreadable file (E-01)
            if not strict:
                continue
            raise CorpusError(f"cannot read {full}: {exc}") from exc
        doc_id = os.path.splitext(name)[0]
        if not text.strip():
            if not strict:
                continue
            raise CorpusError(f"empty document {full!r} (E-01)")
        docs.append(Document(doc_id=doc_id, text=text))
    return docs


def _load_jsonl(path: str, *, strict: bool = True) -> list[Document]:
    docs: list[Document] = []
    with open(path, encoding="utf-8") as handle:
        for lineno, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                if not strict:
                    continue
                raise CorpusError(
                    f"{path}:{lineno} malformed JSON (E-01): {exc}"
                ) from exc
            _emit_doc(obj, path, lineno, docs, strict)
    return docs


def _load_json(path: str, *, strict: bool = True) -> list[Document]:
    try:
        with open(path, encoding="utf-8") as handle:
            obj = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise CorpusError(f"cannot load {path!r} (E-01): {exc}") from exc
    items = obj.get("documents", obj) if isinstance(obj, dict) else obj
    if not isinstance(items, list):
        raise CorpusError(f"{path!r} is not a list/dict of documents (E-01)")
    docs: list[Document] = []
    for i, item in enumerate(items):
        _emit_doc(item, f"{path}[{i}]", i, docs, strict)
    return docs


def _emit_doc(obj, origin, index, out, strict) -> None:
    if not isinstance(obj, dict):
        if not strict:
            return
        raise CorpusError(
            f"{origin}: expected a document object, got {type(obj).__name__}"
        )
    doc_id = str(obj.get("doc_id", index + 1))
    text = obj.get("text", "")
    if not str(text).strip():
        if not strict:
            return
        raise CorpusError(f"{origin}: empty text (E-01)")
    domain = obj.get("domain")
    out.append(Document(doc_id=doc_id, text=str(text), domain=domain))


# ------------------------------------------------------------------- question loading
def load_questions(
    path: str | None = None,
    corpus: list[Document] | None = None,
    *,
    strict: bool = True,
    allow_dangling: bool = False,
    jsonl: str | None = None,
    dataset_jsonl: str | None = None,
    dataset: str | None = None,
) -> list[Question]:
    """Load the grounded question dataset and enforce ground-truth integrity (I-013/E-15).

    Reads `path`/`dataset`/`dataset_jsonl` (a ``.json``/``.jsonl`` of question records, or
    the generated ``questions.json`` with a ``questions`` list). Each record is a
    ``{q_id, question, gold_answer, relevant_docs, tier}``. When `corpus` is given, every
    ``relevant_docs`` id must exist in the corpus; a blank/missing ``relevant_docs`` or an
    id **absent** from the corpus is a load-time ``CorpusError`` (fail fast, not a silent
    0-recall). Pass ``allow_dangling=True`` (or leave `corpus` None) to skip that check.
    """
    target = jsonl or dataset_jsonl or dataset or path or "questions.json"
    records = _load_question_records(target, strict=strict)
    corpus_ids: set[str] | None = (
        {d.doc_id for d in corpus} if corpus is not None else None
    )

    questions: list[Question] = []
    for i, rec in enumerate(records, start=1):
        origin = f"{target}:{i}"
        q = _build_question(rec, origin, i, strict)
        if q is None:
            continue
        relevant = q.relevant_docs
        if not relevant and strict:
            raise CorpusError(f"{origin}: empty relevant_docs (I-013/E-15)")
        if corpus_ids is not None and not allow_dangling:
            missing = [r for r in relevant if r not in corpus_ids]
            if missing:
                raise CorpusError(
                    f"{origin}: relevant_docs {missing!r} absent from the corpus (I-013/E-15/T-15)"
                )
        questions.append(q)
    return questions


def _load_question_records(target: str, *, strict: bool = True) -> list[dict]:
    if target.endswith(".jsonl"):
        out: list[dict] = []
        with open(target, encoding="utf-8") as handle:
            for lineno, raw in enumerate(handle, start=1):
                if raw.strip() == "":
                    continue
                try:
                    out.append(json.loads(raw))
                except json.JSONDecodeError as exc:
                    if not strict:
                        continue
                    raise CorpusError(
                        f"{target}:{lineno} malformed JSON (E-01): {exc}"
                    ) from exc
        return out
    try:
        with open(target, encoding="utf-8") as handle:
            obj = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise CorpusError(f"cannot load {target!r}: {exc}") from exc
    if isinstance(obj, dict):
        return list(obj.get("questions", []))
    if isinstance(obj, list):
        return obj
    raise CorpusError(f"{target!r} is not a list/dict of questions (E-01)")


def _build_question(rec, origin, fallback_index, strict):
    if not isinstance(rec, dict):
        if not strict:
            return None
        raise CorpusError(
            f"{origin}: expected a question object, got {type(rec).__name__}"
        )
    q_id = str(rec.get("q_id", f"q{fallback_index:03d}"))
    text = rec.get("question", "")
    if not str(text).strip():
        if not strict:
            return None
        raise CorpusError(f"{origin}: blank question (I-013/E-15)")
    relevant = rec.get("relevant_docs") or rec.get("relevant_documents") or []
    if not isinstance(relevant, list):
        if not strict:
            return None
        raise CorpusError(f"{origin}: relevant_docs must be a list")
    return Question(
        q_id=q_id,
        question=str(text),
        gold_answer=str(rec.get("gold_answer", "")),
        relevant_docs=[str(r) for r in relevant],
        tier=str(rec.get("tier", "easy")),
    )


# ------------------------------------------------------------------- generation (§17)
# Six domains x six subjects = 36 grounded "cells"; the corpus fills the 100 docs across them
# and the question set is drawn from them with seeded, reproducible choice (R-15).
DOMAINS = {
    "policy": [
        "reimbursement",
        "travel",
        "expense",
        "procurement",
        "leave",
        "overtime",
    ],
    "travel": [
        "hotel",
        "airfare",
        "per_diem",
        "visa",
        "ground_transport",
        "international",
    ],
    "finance": ["credit_limit", "budget", "invoice", "payroll", "refund", "grant"],
    "ops": ["on_call", "incident", "deployment", "retention", "backup", "capacity"],
    "security": ["password", "two_factor", "access", "encryption", "audit", "breach"],
    "hr": [
        "onboarding",
        "compensation",
        "benefits",
        "termination",
        "promotion",
        "conduct",
    ],
}
DOMAIN_NAMES = sorted(DOMAINS)
SCOPES = ["all staff", "executives", "new hires", "contractors", "managers"]
YEARS = [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026, 2027]


def _doc_text(i, rng, domain=None, subject=None, scope=None, amount=None, year=None):
    cell = i
    dom = domain or DOMAIN_NAMES[(i - 1) % len(DOMAIN_NAMES)]
    subj = subject or DOMAINS[dom][(i - 1) % 6]
    if scope is None:
        scope = SCOPES[(i - 1) % len(SCOPES)]
    if amount is None:
        amount = (
            1000 + (i - 1) * 50
        )  # unique per doc, so grounded questions stay distinct
    if year is None:
        year = YEARS[(i - 1) % len(YEARS)]
    stem = f"{i:03d}"
    text = (
        f"{dom} {subj} policy reference {stem}, edition {i}. "
        f"The {subj} limit for {scope} is {amount} dollars, effective {year}. "
        f"Per {dom} annex {subj}-{stem}, this applies to {scope} in the {year} period. "
        f"Cross-reference {dom} {subj} for {scope} budgeting at {amount} each."
    )
    return text, dict(domain=dom, subject=subj, scope=scope, amount=amount, year=year)


def generate_corpus(
    out_dir: str | None = None,
    *,
    n_docs: int = 100,
    seed: int = 42,
    write: bool = True,
) -> tuple[list[Document], dict]:
    """Deterministically author the ~100-doc corpus (R-15/T-01, §15).

      For a fixed `seed` the documents written (or returned) are **byte-identical** across
      runs. Returns ``(docs, info)``: the docs plus the per-doc generation metadata
      (domain/subject/scope/amount/year) used to author the grounded questions. When
      ``out_dir`` is given and ``write`` is True, the corpus is written to ``out_dir``
    (NNN.txt); the JSONL mirror (``corpus.jsonl`` used by `--corpus`) is also written.
    """
    rng = random.Random(seed)
    info: dict[str, Any] = {}
    docs: list[Document] = []
    # A little seeded shuffling of the per-doc attributes so the corpus is less regular,
    # while staying fully deterministic.
    pool = list(range(n_docs))
    order_shuffled = pool[:]
    rng.shuffle(order_shuffled)
    for i in range(1, n_docs + 1):
        text, meta = _doc_text(i, rng)
        # seed a per-doc distinctive token so BM25 can discriminate similar docs
        tag = rng.choice(["alpha", "beta", "gamma", "delta", "omega", "sigma"])
        meta["tag"] = tag
        text = f"{tag} {text}"
        doc = Document(doc_id=f"{i:03d}", text=text, domain=meta["domain"])
        docs.append(doc)
        info[doc.doc_id] = meta

    if write and out_dir is not None:
        _write_corpus(out_dir, docs, info, seed, n_docs)
    return docs, info


def generate_corpus_and_questions(
    out_dir: str | None = None,
    *,
    n_docs: int = 100,
    n_questions: int = 25,
    seed: int = 42,
    write: bool = True,
) -> tuple[list[Document], dict, list[Question]]:
    """Generate the corpus **and** its grounded question set across the §17 tiers (R-10).

    The distribution is non-trivial (T-01b): the four tiers are all present, the
    ``distractor`` questions are anchored to docs that have lexically-similar-but-irrelevant
    siblings in the corpus (§6/§7/§17). Fully deterministic for a fixed `seed` (R-15).
    """
    docs, info = generate_corpus(out_dir, n_docs=n_docs, seed=seed, write=write)
    questions = _generate_questions(docs, info, n_questions=n_questions, seed=seed)
    if write and out_dir is not None:
        _write_questions(out_dir, questions, seed, n_questions, n_docs)
    return docs, info, questions


def _generate_questions(
    docs,
    info,
    *,
    n_questions,
    seed,
):
    """Author the grounded question set deterministically (R-10/T-01b)."""
    rng = random.Random(seed ^ 0x5A)
    by_domain: dict[str, list[str]] = {}
    for doc in docs:
        m = info[doc.doc_id]
        by_domain.setdefault(m["domain"], []).append(doc.doc_id)
    for dom in by_domain:
        by_domain[dom].sort()

    # Split the 25 across tiers with a non-trivial, all-present distribution.
    dist = {"easy": 8, "multi": 6, "synthesis": 5, "distractor": 6}
    total = sum(dist.values())
    if n_questions != total:
        # Scale roughly but keep every tier non-empty; deterministic for the default 25.
        base = max(1, n_questions // len(dist))
        dist = {t: base for t in dist}
    excess = n_questions - sum(dist.values())
    # spread any excess round-robin
    order = list(dist.keys())
    idx = 0
    while excess > 0:
        dist[order[idx % len(order)]] += 1
        excess -= 1
        idx += 1

    seen: set[str] = set()
    records: list[dict] = []
    counter = 0
    # Fill each tier with UNIQUE questions (dedupe during generation, not after) so the
    # final count equals n_questions and every tier stays non-empty (R-10/T-01b), via per-generation dedupe.
    for tier, count in dist.items():
        made = 0
        tries = 0
        while made < count and tries < count * 200:
            tries += 1
            m = _make_question(rng, by_domain, info, tier)
            if m is None or m["question"] in seen:
                continue
            seen.add(m["question"])
            counter += 1
            records.append(
                {
                    "q_id": f"{tier[0]}{counter:03d}",
                    "question": m["question"],
                    "gold_answer": m["gold_answer"],
                    "relevant_docs": m["relevant_docs"],
                    "tier": tier,
                }
            )
            made += 1
    keys = ("q_id", "question", "gold_answer", "relevant_docs", "tier")
    return [Question(**{k: r[k] for k in keys}) for r in records]


def _make_question(rng, by_domain, info, tier):
    """Craft one grounded question for `tier` from the corpus metadata. Returns None if the
    corpus has no suitable docs (e.g. <2 in a domain for `multi`/`synthesis`)."""
    domains = [d for d in by_domain if by_domain[d]]
    if not domains:
        return None
    if tier == "easy":
        dom = rng.choice(domains)
        did = rng.choice(by_domain[dom])
        m = info[did]
        q = (
            f"What is the {m['subject']} limit for {m['scope']} in {m['domain']} "
            f"for {m['year']}, at the {m['amount']}-dollar figure?"
        )
        gold = f"{m['amount']} dollars"
        return {
            "question": q,
            "gold_answer": gold,
            "relevant_docs": [did],
            "tier": tier,
        }

    if tier == "multi":
        dom = rng.choice([d for d in domains if len(by_domain[d]) >= 2] or None)
        if dom is None:
            return None
        ids = by_domain[dom]
        a, b = sorted(rng.sample(ids, 2))
        ma, mb = info[a], info[b]
        q = (
            f"What are the {ma['subject']} and {mb['subject']} limits for {ma['scope']} "
            f"in {dom} across {ma['year']} and {mb['year']} ({ma['amount']} and {mb['amount']})?"
        )
        gold = f"{ma['amount']} and {mb['amount']} dollars"
        return {
            "question": q,
            "gold_answer": gold,
            "relevant_docs": [a, b],
            "tier": tier,
        }

    if tier == "synthesis":
        # Combine up to 3 docs across domains; the answer must synthesize them.
        picks: list[str] = []
        used_dom: set[str] = set()
        for _ in range(3):
            d = rng.choice([d for d in domains if d not in used_dom])
            used_dom.add(d)
            picks.append(rng.choice(by_domain[d]))
        picks = sorted(set(picks))
        parts = [f"{info[p]['amount']}" for p in picks]
        q = (
            f"Combining the {info[picks[0]]['subject']} and {info[picks[-1]]['subject']} "
            f"limits for {info[picks[0]]['scope']}, what total applies ({', '.join(parts)})?"
        )
        gold = f"sum {', '.join(parts)} dollars"
        return {
            "question": q,
            "gold_answer": gold,
            "relevant_docs": picks,
            "tier": tier,
        }

    if tier == "distractor":
        # A real target doc PLUS lexically-similar siblings in the same cell that are NOT
        # relevant (§6/§7/§17 context-pollution regime).
        dom = rng.choice([d for d in domains if len(by_domain[d]) >= 2] or domains)
        target = rng.choice(by_domain[dom])
        siblings = [d for d in by_domain[dom] if d != target]
        siblings.sort()
        m = info[target]
        q = (
            f"Which {dom} {m['subject']} limit, at the {m['amount']} figure, applies to "
            f"{m['scope']} for {m['year']}, ignoring similar {dom} {m['subject']} references?"
        )
        gold = f"{m['amount']} dollars"
        return {
            "question": q,
            "gold_answer": gold,
            "relevant_docs": [target],
            "tier": tier,
        }

    return None


# ------------------------------------------------------------------- artifact writing
def _write_directory(out_dir: str) -> str:
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError as exc:
        raise CorpusError(f"cannot create {out_dir!r} (E-01): {exc}") from exc
    return out_dir


def _write_corpus(out_dir, docs, info, seed, n_docs) -> None:
    directory = os.path.join(out_dir, "documents")
    try:
        os.makedirs(directory, exist_ok=True)
    except OSError as exc:
        raise CorpusError(f"cannot create {directory!r} (E-01): {exc}") from exc
    try:
        for doc in docs:
            with open(
                os.path.join(directory, f"{doc.doc_id}.txt"), "w", encoding="utf-8"
            ) as h:
                h.write(doc.text)
        jsonl_path = os.path.join(out_dir, "corpus.jsonl")
        with open(jsonl_path, "w", encoding="utf-8") as h:
            for doc in docs:
                m = info[doc.doc_id]
                row = {
                    "doc_id": doc.doc_id,
                    "text": doc.text,
                    "domain": m["domain"],
                }
                h.write(json.dumps(row, sort_keys=True) + "\n")
    except OSError as exc:
        raise CorpusError(f"cannot write corpus to {out_dir!r} (E-01): {exc}") from exc


def _write_questions(out_dir, questions, seed, n_questions, n_docs) -> None:
    by_tier: dict[str, int] = {}
    for q in questions:
        by_tier[q.tier] = by_tier.get(q.tier, 0) + 1
    payload = {
        "meta": {
            "seed": seed,
            "n_docs": n_docs,
            "n_questions": n_questions,
            "tiers": by_tier,
            "schema": "rag-eval/questions/v0.1",
        },
        "questions": [
            {
                "q_id": q.q_id,
                "question": q.question,
                "gold_answer": q.gold_answer,
                "relevant_docs": q.relevant_docs,
                "tier": q.tier,
            }
            for q in questions
        ],
    }
    path = os.path.join(out_dir, "questions.json")
    try:
        with open(path, "w", encoding="utf-8") as h:
            json.dump(payload, h, indent=2, sort_keys=True)
            h.write("\n")
    except OSError as exc:
        raise CorpusError(f"cannot write {path!r} (E-01): {exc}") from exc


__all__ = [
    "CorpusError",
    "DOMAINS",
    "DOMAIN_NAMES",
    "generate_corpus",
    "generate_corpus_and_questions",
    "load_corpus",
    "load_questions",
]
