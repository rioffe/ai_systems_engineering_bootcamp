"""R-11 / §5.1 -- `rag-eval`: the primary product surface.

Subcommands, all offline by default via ``MockLLM`` + ``MockJudge`` (K-01/T-14):

* ``gen-corpus`` -- generate the ~100-doc corpus + grounded ``questions.json`` (R-10/T-01).
* ``eval``       -- run the full pipeline over the dataset and emit a metrics report with a
    per-tier breakdown (§9.5). ``--judge off`` makes it a retrieval-only eval (R-12).
* ``show``       -- print one case's retrieval + context + answer + verdict (diagnostic).

Backend selection (E-11/E-12/E-13): with ``--mock`` (or when no model is forced and Ollama
is unreachable) the run degrades to the offline doubles with a banner; a forced, unreachable
or unpulled model is a fatal ``EXIT_BACKEND``. Load failures are ``EXIT_LOAD``; bad usage is
``EXIT_BAD_USAGE`` (argparse). A per-case fault is a *result* carried in the report, not a
failing exit code (run-all default; §3.1).
"""

from __future__ import annotations

import argparse
import json
import sys

from .corpus import (
    CorpusError,
    generate_corpus_and_questions,
    load_corpus,
    load_questions,
)
from .judgment import Judge, MockJudge, OllamaJudge
from .model import (
    LLM,
    MockLLM,
    OllamaClient,
    OllamaError,
    OllamaLLM,
    model_not_found_error,
)
from .pipeline import CaseRun, RunReport, run_case, run_dataset
from .retrieval import BM25Retriever
from .types import Question

# K-03 defaults.
DEFAULT_MODEL = "qwen3.8:27b-mlx"
DEFAULT_CORPUS = "documents"
DEFAULT_DATASET = "questions.json"
DEFAULT_REPORT = "report.json"
DEFAULT_K = 5
DEFAULT_BUDGET = 2000
DEFAULT_N_DOCS = 100
DEFAULT_N_QUESTIONS = 25
DEFAULT_SEED = 42

# §5.1 exit codes.
EXIT_BAD_USAGE = 2
EXIT_LOAD = 3
EXIT_BACKEND = 4

OFF = {"off", "false", "0", "no"}


class Backend:
    """The selected generation+judging backend, plus its banner / fatal exit code."""

    def __init__(
        self,
        llm: LLM | None,
        judge: Judge | None,
        label: str | None,
        banner: str | None = None,
        exit_code: int | None = None,
    ) -> None:
        self.llm = llm
        self.judge = judge
        self.label = label
        self.banner = banner
        self.exit_code = exit_code


# ------------------------------------------------------------------ backend selection
def _model_available(pulled: list[str], model: str) -> bool:
    # A model is "pulled" if an exact tag or a same-family tag (before the ':') matches.
    base = model.split(":")[0]
    return any(name == model or name.split(":")[0] == base for name in pulled)


def select_backend(args: argparse.Namespace) -> Backend:
    # E-11/E-12/E-13: --mock forces the offline path; a forced model that is unreachable
    # or unpulled is a fatal EXIT_BACKEND; an unforced model falls back to mock + banner.
    if getattr(args, "mock", False):
        return Backend(
            MockLLM(),
            MockJudge(),
            "mock (offline)",
            banner="using the offline MockLLM/MockJudge pipeline",
        )

    model = args.model or DEFAULT_MODEL
    forced = args.model is not None
    try:
        client = OllamaClient()
        pulled = client.list_models()
    except OllamaError:
        if forced:
            return Backend(
                None,
                None,
                None,
                banner="ollama not reachable; re-run with --mock or start ollama",
                exit_code=EXIT_BACKEND,
            )
        return Backend(
            MockLLM(),
            MockJudge(),
            "mock (offline)",
            banner="Ollama unavailable — using mock pipeline",
        )

    if not _model_available(pulled, model):
        return Backend(
            None,
            None,
            None,
            banner=model_not_found_error(model),
            exit_code=EXIT_BACKEND,
        )
    label = f"ollama {model}"
    return Backend(
        OllamaLLM(model, client=client), OllamaJudge(model, client=client), label
    )


# ------------------------------------------------------------------ corpus generation
def cmd_gen_corpus(args: argparse.Namespace) -> int:
    out_dir = args.out
    docs, info, questions = generate_corpus_and_questions(
        out_dir,
        n_docs=args.n_docs,
        n_questions=args.n_questions,
        seed=args.seed,
    )
    if not getattr(args, "quiet", False):
        by_tier: dict[str, int] = {}
        for q in questions:
            by_tier[q.tier] = by_tier.get(q.tier, 0) + 1
        print(
            f"generated {len(docs)} documents and {len(questions)} questions "
            f"(seed {args.seed}) under {out_dir!r}: tiers {by_tier}",
            flush=True,
        )
    return 0


# ------------------------------------------------------------------ eval
def _progress(quiet: bool):
    # Per-case progress to stderr (§3.2) unless --quiet; a live marker, not a result.
    def step(question: Question, row) -> None:
        if quiet:
            return
        p = "none" if row.precision is None else f"{row.precision:.2f}"
        r = "none" if row.recall is None else f"{row.recall:.2f}"
        print(f"  {row.q_id} [{row.status}] p={p} r={r}", file=sys.stderr, flush=True)

    return step


def cmd_eval(args: argparse.Namespace) -> int:
    backend = select_backend(args)
    if backend.exit_code is not None:
        if not getattr(args, "quiet", False):
            print(backend.banner, file=sys.stderr, flush=True)
        return backend.exit_code
    assert backend.llm is not None and backend.judge is not None

    # Load-time errors fail fast with EXIT_LOAD (E-01/E-15/T-15) -- never a silent 0-recall.
    try:
        docs = load_corpus(args.corpus)
        questions = load_questions(args.dataset, corpus=docs)
    except CorpusError as exc:
        print(f"load error: {exc}", file=sys.stderr, flush=True)
        return EXIT_LOAD

    retriever = BM25Retriever(docs)
    tiers = _parse_tiers(args.tiers)
    judge_on = args.judge not in OFF

    # E-17: a --tiers subset matching zero questions is a warning + empty report, not a crash.
    if (
        tiers is not None
        and not any(q.tier in tiers for q in questions)
        and not getattr(args, "quiet", False)
    ):
        print(
            f"warning: --tiers {sorted(tiers)} matched no questions; empty report",
            file=sys.stderr,
            flush=True,
        )

    meta = {
        "command": "eval",
        "backend": backend.label,
        "model": getattr(args, "model", None),
        "mock": bool(getattr(args, "mock", False)),
        "k": args.k,
        "token_budget": args.budget,
        "max_tokens": getattr(args, "max_tokens", 512),
        "judge": judge_on,
        "seed": args.seed,
        "tiers": sorted(tiers) if tiers is not None else "all",
        "n_questions": len(questions),
    }
    report = run_dataset(
        questions,
        retriever,
        backend.llm,
        backend.judge,
        k=args.k,
        token_budget=args.budget,
        judge_on=judge_on,
        tiers=tiers,
        stop_on_error=getattr(args, "stop_on_error", False),
        seed=args.seed,
        max_tokens=getattr(args, "max_tokens", 512),
        meta=meta,
        on_progress=_progress(getattr(args, "quiet", False)),
    )

    # Coverage / truncation: surfaced so a headline accuracy can't hide failed cases.
    meta["n_judged"] = sum(1 for r in report.rows if r.correct is not None)
    meta["n_failed"] = sum(1 for r in report.rows if r.status != "SCORED")
    meta["n_truncated"] = sum(1 for r in report.rows if r.answer_status == "TRUNCATED")

    # Machine-readable report (--out; default report.json) with per-case rows + aggregate.
    if args.out:
        path = args.out
        payload = json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.write("\n")
        except OSError as exc:
            print(
                f"could not write report to {path!r}: {exc}",
                file=sys.stderr,
                flush=True,
            )
            return EXIT_LOAD

    if not getattr(args, "quiet", False):
        if backend.banner:
            print(f"[{backend.banner}] {backend.label}", flush=True)
        _render_summary(report, out_path=args.out or DEFAULT_REPORT)
    return 0


# ------------------------------------------------------------------ show
def cmd_show(args: argparse.Namespace) -> int:
    backend = select_backend(args)
    if backend.exit_code is not None:
        if not getattr(args, "quiet", False):
            print(backend.banner, file=sys.stderr, flush=True)
        return backend.exit_code

    try:
        docs = load_corpus(args.corpus)
        questions = load_questions(args.dataset, corpus=docs)
    except CorpusError as exc:
        print(f"load error: {exc}", file=sys.stderr, flush=True)
        return EXIT_LOAD

    if not questions:
        print("no questions in dataset", file=sys.stderr, flush=True)
        return EXIT_LOAD
    question = _pick_question(questions, getattr(args, "qid", None))

    retriever = BM25Retriever(docs)
    judge_on = args.judge not in OFF
    case = run_case(
        question,
        retriever,
        backend.llm,
        backend.judge,
        k=args.k,
        token_budget=args.budget,
        judge_on=judge_on,
        seed=args.seed,
        max_tokens=getattr(args, "max_tokens", 512),
    )
    if getattr(args, "as_json", False):
        print(json.dumps(case.to_detail(), indent=2, ensure_ascii=False))
        return 0
    _render_case(case)
    return 0


# ------------------------------------------------------------------ report rendering
def _render_summary(report: RunReport, out_path: str | None = None) -> None:
    agg = report.aggregate
    n_judged = sum(1 for r in report.rows if r.correct is not None)
    n_failed = sum(1 for r in report.rows if r.status != "SCORED")
    n_truncated = sum(1 for r in report.rows if r.answer_status == "TRUNCATED")
    trunc_note = (
        f" ({n_truncated} truncated - raise --max-tokens)" if n_truncated else ""
    )
    lines = [
        f"cases: {agg.n_cases}",
        f"coverage: {n_judged}/{agg.n_cases} judged; {n_failed} failed{trunc_note}",
        f"precision: {agg.precision:.3f}",
        f"recall:    {agg.recall:.3f}",
        f"f1:        {agg.f1:.3f}",
        f"answer_accuracy: {agg.answer_accuracy:.3f}",
        f"hallucination_rate: {agg.hallucination_rate:.3f}",
        "failure_breakdown: "
        + " ".join(f"{k}={v}" for k, v in agg.failure_breakdown.items()),
    ]
    if agg.by_tier:
        lines.append("by_tier:")
        for tier in sorted(agg.by_tier):
            t = agg.by_tier[tier]
            lines.append(
                f"  {tier:<10} n={t.n_cases:<3} p={t.precision:.3f} "
                f"r={t.recall:.3f} acc={t.answer_accuracy:.3f} "
                f"hall={t.hallucination_rate:.3f}"
            )
    if out_path:
        lines.append(f"report: {out_path}")
    print("\n".join(lines), flush=True)


def _render_case(case: CaseRun) -> None:
    detail = case.to_detail()
    print(
        f"Q {detail['q_id']} [{detail['tier']}]  {case.row.status}"
        + (
            f"  (failure_stage={case.row.failure_stage})"
            if case.row.failure_stage
            else ""
        )
    )
    print(f"  question: {detail['question']}")
    print(f"  gold:     {detail['gold_answer']}")
    print(f"  relevant: {', '.join(detail['relevant_docs'])}")
    print(
        f"  retrieved@{case.row.retrieved} (p={case.row.precision} r={case.row.recall} "
        f"f1={case.row.f1}, tokens={case.row.context_tokens}, truncated={case.row.truncated})"
    )
    for hit in detail["retrieved"]:
        flag = " *" if hit["doc_id"] in detail["relevant_docs"] else "  "
        print(f"   {flag}[{hit['rank']}] {hit['doc_id']}  score={hit['score']}")
    if detail.get("answer"):
        a = detail["answer"]
        print(
            f"  answer:   {a['text']!r} (confidence {a['confidence']}, sources {a['sources']})"
        )
    if detail.get("verdict"):
        v = detail["verdict"]
        print(
            f"  verdict:  correct={v['correct']} supported={v['supported']} "
            f"complete={v['complete']} unsupported={len(v['unsupported_claims'])}/"
            f"{v['total_factual_claims']} :: {v['rationale']}"
        )


# ------------------------------------------------------------------ argument parsing
def _parse_tiers(raw: str | None) -> set[str] | None:
    # --tiers "easy,multi" -> {"easy","multi"}; absent -> None (all tiers, §17).
    if not raw:
        return None
    return {t.strip() for t in raw.split(",") if t.strip()}


def _pick_question(questions: list[Question], qid: str | None) -> Question:
    if not qid:
        return questions[0]
    for q in questions:
        if q.q_id == qid:
            return q
    raise CorpusError(f"question {qid!r} not found in the dataset")


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--dataset", default=DEFAULT_DATASET, help="questions.json path")
    p.add_argument("--corpus", default=DEFAULT_CORPUS, help="document dir or .jsonl")
    p.add_argument("--k", type=int, default=DEFAULT_K, help="retrieval top-k")
    p.add_argument(
        "--budget",
        type=int,
        default=DEFAULT_BUDGET,
        help="retrieval token budget B_retrieval",
    )
    p.add_argument(
        "--max-tokens",
        type=int,
        default=512,
        help="generation+judge num_predict; raise for thinking models "
        "(e.g. --max-tokens 2048) to clear the hidden thinking phase",
    )
    p.add_argument(
        "--tiers", default=None, help="comma list of §17 tiers (default: all)"
    )
    p.add_argument(
        "--model",
        default=None,
        help=f"Ollama model for generate+judge (default {DEFAULT_MODEL})",
    )
    p.add_argument(
        "--judge",
        default="on",
        choices=["on", "off"],
        help="run LLM-as-judge (default on); off = retrieval-only eval",
    )
    p.add_argument(
        "--mock",
        action="store_true",
        help="force the offline MockLLM+MockJudge path (no Ollama, no network)",
    )
    p.add_argument(
        "--seed", type=int, default=DEFAULT_SEED, help="determinism seed (R-15)"
    )
    p.add_argument(
        "--stop-on-error",
        action="store_true",
        help="abort after the first non-terminal fault (default: run all)",
    )
    p.add_argument(
        "--quiet", action="store_true", help="suppress per-case stderr progress"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rag-eval",
        description="RAG eval harness: BM25 retrieval + LLM-as-judge over a grounded dataset.",
    )
    sub = parser.add_subparsers(dest="command")

    # eval
    p_eval = sub.add_parser(
        "eval", help="run the full pipeline and emit a metrics report"
    )
    _add_common(p_eval)
    p_eval.add_argument(
        "--out", default=DEFAULT_REPORT, help="write the JSON report here"
    )
    p_eval.set_defaults(func=cmd_eval)

    # gen-corpus
    p_gen = sub.add_parser(
        "gen-corpus", help="generate the ~100-doc corpus + grounded questions.json"
    )
    p_gen.add_argument("--out", default="corpus", help="output directory")
    p_gen.add_argument("--n-docs", type=int, default=DEFAULT_N_DOCS)
    p_gen.add_argument("--n-questions", type=int, default=DEFAULT_N_QUESTIONS)
    p_gen.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p_gen.add_argument("--quiet", action="store_true")
    p_gen.set_defaults(func=cmd_gen_corpus)

    # show
    p_show = sub.add_parser(
        "show", help="print one case's retrieval + context + answer + verdict"
    )
    _add_common(p_show)
    p_show.add_argument("--qid", default=None, help="question id (default: first)")
    p_show.add_argument("--as-json", action="store_true", help="emit the case as JSON")
    p_show.set_defaults(func=cmd_show)

    return parser


def run(argv: list[str] | None = None) -> int:
    # The CLI entry point. argparse bad-usage -> SystemExit(2) -> EXIT_BAD_USAGE.
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else EXIT_BAD_USAGE
    if getattr(args, "func", None) is None:
        parser.print_help()
        return EXIT_BAD_USAGE
    try:
        return int(args.func(args))
    except CorpusError as exc:
        print(f"load error: {exc}", file=sys.stderr, flush=True)
        return EXIT_LOAD


__all__ = [
    "Backend",
    "build_parser",
    "cmd_eval",
    "cmd_gen_corpus",
    "cmd_show",
    "run",
    "select_backend",
]
