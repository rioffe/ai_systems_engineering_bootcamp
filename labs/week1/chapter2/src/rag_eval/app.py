"""App entry point (SPEC §5.1 / `rag-eval = rag_eval.app:main`).

A thin shim over :func:`rag_eval.cli.run`: it owns the process-level contract (parse argv,
dispatch the §5.1 subcommand, map to the documented exit codes) and exposes ``main`` for
the ``rag-eval`` console script. The logic lives in ``cli.py`` so the surface stays small.
"""

from __future__ import annotations

import argparse
import os
import sys

from .cli import EXIT_LOAD, run


def main(argv: list[str] | None = None) -> int:
    """The console-script entry point. Returns the documented §5.1 exit code."""
    return run(argv)


def _first_existing(candidates) -> str | None:
    """The first existing path in ``candidates`` (skipping None), or None."""
    for path in candidates:
        if path is not None and os.path.exists(path):
            return path
    return None


def _load_pipeline_assets(corpus: str | None, dataset: str | None) -> tuple:
    """Discover + load the corpus and grounded questions, building the BM25 retriever.

    Mirrors the CLI's ``load_corpus``/``load_questions`` fail-fast (E-01/E-15/T-15): the
    GUI must never launch with a missing retriever, because an empty/``None`` retriever
    is a silent 0-recall -- the eval's single worst failure mode. ``--corpus`` /
    ``--dataset`` override auto-discovery, which probes both the corpus dir
    (``documents`` / ``questions.json`` -- e.g. the lab's ``corpus/``) and the lab root,
    so the panel works whether it is launched from the corpus dir or the chapter root.
    Imports (stdlib-only deterministic boundary) are lazy so this helper need not be
    imported to launch the CLI.
    """
    from .corpus import CorpusError, load_corpus, load_questions
    from .retrieval import BM25Retriever

    corpus_path = _first_existing(
        [corpus, "documents", "corpus/documents", "corpus.jsonl", "corpus/corpus.jsonl"]
    )
    if corpus_path is None:
        raise CorpusError(
            "no corpus found -- pass --corpus (a documents dir or .jsonl); looked for: "
            "documents, corpus/documents, corpus.jsonl, corpus/corpus.jsonl"
        )
    dataset_path = _first_existing([dataset, "questions.json", "corpus/questions.json"])
    docs = load_corpus(corpus_path)
    questions = load_questions(dataset_path, corpus=docs) if dataset_path else []
    return BM25Retriever(docs), questions


def main_gui(argv: list[str] | None = None) -> int:
    """`rag-gui` entry point: the optional PyQt5 one-question eval panel (R-13).

    Imports PyQt5 lazily so the package and the `rag-eval` CLI stay importable without a
    Qt install (I-011); the window is launched only when this surface is invoked, and it
    discovers Ollama but degrades to the offline mocks when the daemon is unreachable.
    The corpus + grounded questions are loaded up front (fail fast on a missing/partial
    corpus, E-01/E-15) so the panel always runs with a real retriever; ``--corpus`` /
    ``--dataset`` override auto-discovery.
    """
    parser = argparse.ArgumentParser(
        prog="rag-gui",
        description="RAG eval -- the optional one-question PyQt5 panel (ch2, section 1).",
    )
    parser.add_argument(
        "--corpus", default=None, help="document dir or .jsonl (default: auto-discover)"
    )
    parser.add_argument(
        "--dataset", default=None, help="questions.json path (default: auto-discover)"
    )
    parser.add_argument("--model", default=None, help="Ollama model name")
    parser.add_argument(
        "--host", default=None, help="Ollama base URL (default: :11434)"
    )
    args, _ = parser.parse_known_args(argv)
    raw = argv if argv is not None else sys.argv[1:]

    # Build the deterministic retriever + grounded questions up front: a missing or
    # partial corpus is a fail-fast EXIT_LOAD, not a broken window with a 0-recall run.
    try:
        retriever, questions = _load_pipeline_assets(args.corpus, args.dataset)
    except Exception as exc:  # CorpusError and any load-time fault -> EXIT_LOAD
        print(f"load error: {exc}", file=sys.stderr, flush=True)
        return EXIT_LOAD

    from PyQt5.QtWidgets import QApplication

    from .ui import MainWindow

    app = QApplication(raw)
    window = MainWindow(
        retriever=retriever,
        questions=questions,
        model=args.model,
        ollama_host=args.host,
    )
    window.show()
    return app.exec_()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())


__all__ = ["main", "main_gui"]
