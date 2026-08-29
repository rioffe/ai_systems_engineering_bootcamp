"""rag -- the primary CLI surface (SPEC section 5.1, R-14).

Subcommands:
    build-index  chunk + (contextualize +) embed + index the corpus (INDEX-TIME, F-003).
    eval         run the full section-22 pipeline over a question dataset, emit a report.
    gen-corpus   generate the sectioned corpus + grounded questions.json (R-13).
    show         print one case's ranked -> reranked -> contextual evidence + verdict.

Exit codes (R-15 / section 5.1):
     0  ran (even when some cases errored -- errors are *recorded* rows, not failures)
     2  bad CLI usage (e.g. --top-n < --k, E-15; argparse usage errors)
     3  corpus / questions / index load failure (E-01 / E-14 / I-013)
     4  PULL_REQUIRED -- backend reachable but requested model is not pulled, and
        --mock was NOT requested (fatal backend failure; --mock papers over it)

Code is kept at strict 4/8/12-space indents. Explanations are `#` comments,
which Python's tokenizer ignores for indentation, so notes can never break a
file by shifting an indent level the way a docstring statement can.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys

from rag.availability import resolve_availability
from rag.corpus import generate_corpus_and_questions, load_corpus, load_questions
from rag.embedding import MockEmbedder, OllamaEmbedder
from rag.judgment import MockJudge, OllamaJudge
from rag.logging_setup import configure
from rag.metrics import aggregate
from rag.model import MockLLM, OllamaLLM
from rag.pipeline import build_index, run_case, run_dataset
from rag.schemas import using_jsonschema

DEGRADED_MOCK = (
        "DEGRADED_MOCK: no live Ollama backend; "
        "running on deterministic doubles (offline-safe)."
)
PULL_REQUIRED = (
        "PULL_REQUIRED: cannot use the Ollama backend for {model!r}; "
        "run `ollama pull {model!r}` or pass --mock."
)
INJECTION_BANNER = (
        "INJECTION! {n} chunk(s) flagged {ids} -- "
        "payload treated as data, not instructions"
)


def _availability_banner(ns):
# E-13 / R-19 / F-013: resolve the canonical outcome before any work, print its
# distinct banner, record use_mock, return its exit code. --mock forces DEGRADED_MOCK.
    outcome = resolve_availability([ns.model, ns.embed_model], mock=ns.mock)
    if outcome.banner and not ns.quiet:
        sys.stderr.write(outcome.banner + "\n")
    ns.use_mock = outcome.use_mock
    return outcome.exit_code


def _select_llm(model_name, mock):
    return MockLLM() if mock else OllamaLLM(model=model_name)


def _select_judge(model_name, mock):
    return MockJudge() if mock else OllamaJudge(model=model_name)


def _select_embedder(embed_model, mock):
    return MockEmbedder() if (mock or embed_model == "mock") else OllamaEmbedder(model=embed_model)


def _serialize(obj):
    """Recursively convert dataclasses / sets to JSON-native structures."""
    if hasattr(obj, "__dataclass_fields__") and not isinstance(obj, type):
        return {f: _serialize(getattr(obj, f)) for f in obj.__dataclass_fields__}
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize(v) for v in obj]
    if isinstance(obj, (set, frozenset)):
        return sorted(_serialize(v) for v in obj)
    return obj


def _injection_banner(rows):
    """The section-18 / E-16 banner if any row flagged injection, else None."""
    flagged = [r.q_id for r in rows if r.injection_warning]
    if not flagged:
        return None
    return INJECTION_BANNER.format(n=len(flagged), ids=flagged)


def _summary_lines(agg, k):
    """Human-readable per-metric means + breakdowns (R-14.1)."""
    means = agg.means()
    out = ["RAG eval report -- per-metric means over non-None rows"]
    names = ("precision", "recall", "mrr", "ap", "ndcg", "faithfulness",
            "completeness", "citation_quality")
    for name in names:
        val = means.get(name)
        label = name if name in ("mrr", "faithfulness", "completeness", "citation_quality") else f"{name}@{k}"
        rendered = "n/a" if val is None else f"{val:.4f}"
        out.append("    " + label + ": " + rendered)
    if agg.failure_breakdown:
        out.append("  failure_breakdown (failure_stage -> count, R-15):")
        for stage, count in sorted(agg.failure_breakdown.items()):
            out.append("    " + stage + ": " + str(count))
    if agg.by_tier:
        out.append("  by_tier:")
        for tier, tm in sorted(agg.by_tier.items()):
            tmean = tm.means()
            out.append("    " + tier + " (n=" + str(tm.n) + "): " + str(
                {"precision": tmean.get("precision"), "ndcg": tmean.get("ndcg")}))
    out.append("  schema_validation: " + ("jsonschema" if using_jsonschema() else "structural"))
    return out


def _emit_report(out_path, rows, agg, k, extra):
    """Machine-readable JSON report (R-14.2): rows + AggregateMetrics + context."""
    report = {
        "k": k,
        "n_cases": agg.n,
        "rows": _serialize(rows),
        "aggregate": _serialize(agg),
        "schema_validation": "jsonschema" if using_jsonschema() else "structural",
    }
    report.update(extra)
    if out_path:
        try:
            with open(out_path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(report, indent=2))
        except OSError as exc:
            sys.stderr.write(
                "WARN: could not write report " + repr(out_path) + ": " + str(exc) + "\n"
                )
    return report


def cmd_gen_corpus(ns):
    out_dir = ns.outdir if ns.outdir else "."
    generate_corpus_and_questions(
        out_dir=out_dir,
        n_docs=ns.n_docs,
        n_questions=ns.n_questions,
        seed=ns.seed,
        failure_mode_docs=ns.failure_mode_docs.split(",") if ns.failure_mode_docs else None,
    )
    if not ns.quiet:
        sys.stdout.write("generated corpus + questions into " + out_dir + " (seed=" + str(ns.seed) + ")\n")
    return 0


def _build_for(ns):
    """Index-time build (F-003): load corpus -> chunk -> (contextual) -> embed -> index."""
    docs = load_corpus(ns.corpus)
    index = build_index(
        docs,
        strategy=ns.strategy,
        contextual=ns.contextual,
        embedder=_select_embedder(ns.embed_model, getattr(ns, "use_mock", ns.mock)),
        overlap=ns.overlap,
        chunk_size=ns.chunk_size,
        embed_model=ns.embed_model,
        mock=getattr(ns, "use_mock", ns.mock),
    )
    return docs, index


def cmd_build_index(ns):
    _, index = _build_for(ns)
    n = len(index[0]._data)
    line = ("built index: " + str(n) + " chunks strategy=" + ns.strategy
            + " contextual=" + str(ns.contextual) + " overlap=" + str(ns.overlap)
            + " mock=" + str(ns.mock))
    if not ns.quiet:
        sys.stdout.write(line + "\n")
    return 0


def cmd_eval(ns):
    ec = _availability_banner(ns)
    if ec != 0:
        return ec
    _, index = _build_for(ns)
    chunk_ids = set(index[0]._data.keys())
    questions = load_questions(ns.dataset, allowed_chunk_ids=chunk_ids)
    if ns.tiers:
        wanted = set(ns.tiers)
        questions = [q for q in questions if getattr(q, "tier", None) in wanted]
    llm = _select_llm(ns.model, ns.use_mock)
    judge = None if not ns.judge else _select_judge(ns.model, ns.use_mock)
    rows = run_dataset(
        questions,
        index,
        hybrid=ns.hybrid,
        alpha=ns.alpha,
        rerank=ns.rerank,
        top_n=ns.top_n,
        top_k=ns.k,
        expand=ns.expand,
        n_expand=ns.n_expand,
        judge=judge,
        llm=llm,
    )
    agg = aggregate(rows, k=ns.k)
    banner = _injection_banner(rows)
    if not ns.quiet:
        sys.stdout.write("\n".join(_summary_lines(agg, ns.k)) + "\n")
    if banner and ns.show_banners:
        sys.stderr.write(banner + "\n")
    _emit_report(ns.out, rows, agg, ns.k, {"injection_banner": banner, "tiers": list(ns.tiers or [])})
    return 0


def cmd_show(ns):
    ec = _availability_banner(ns)
    if ec != 0:
        return ec
    _, index = _build_for(ns)
    questions = load_questions(ns.dataset, allowed_chunk_ids=set(index[0]._data.keys()))
    qid = ns.qid or (questions[0].q_id if questions else None)
    if qid is None:
        sys.stderr.write("no question matched --qid\n")
        return 3
    q = next((x for x in questions if x.q_id == qid), None)
    if q is None:
        sys.stderr.write("question " + repr(qid) + " not found\n")
        return 3
    rows = run_case(
        q,
        index,
        hybrid=ns.hybrid,
        alpha=ns.alpha,
        rerank=ns.rerank,
        top_n=ns.top_n,
        top_k=ns.k,
        expand=ns.expand,
        n_expand=ns.n_expand,
        judge=None if not ns.judge else _select_judge(ns.model, ns.use_mock),
        llm=_select_llm(ns.model, ns.use_mock),
    )
    m = rows
    sys.stdout.write("[" + m.q_id + "] status=" + str(m.status) + " failure_stage=" + str(m.failure_stage) + "\n")
    sys.stdout.write("  retrieved: " + str(m.retrieved) + "\n")
    if m.injection_warning:
        sys.stdout.write(INJECTION_BANNER.format(n=1, ids=[m.q_id]) + "\n")
    return 0


def _parse_onoff(val):
    if val in ("on", "true", "1", "yes"):
        return True
    if val in ("off", "false", "0", "no"):
        return False
    raise argparse.ArgumentTypeError("expected on|off, got " + repr(val))


def _add_common(p):
    """The shared section-5.1 option set."""
    p.add_argument("--dataset", default=os.environ.get("RAG_DATASET", "questions.json"))
    p.add_argument("--corpus", default=os.environ.get("RAG_CORPUS", "documents"))
    p.add_argument("--out", default="report.json", help="JSON report path (empty = skip)")
    p.add_argument("--k", type=int, default=5)
    p.add_argument("--top-n", type=int, default=20)
    p.add_argument("--alpha", type=float, default=0.5)
    p.add_argument("--hybrid", type=_parse_onoff, default=False)
    p.add_argument("--rerank", type=_parse_onoff, default=False)
    p.add_argument("--llm-rerank", action="store_true")
    p.add_argument("--expand", type=_parse_onoff, default=False)
    p.add_argument("--n-expand", type=int, default=3)
    p.add_argument("--llm-expand", action="store_true")
    p.add_argument("--strategy", choices=["heading", "fixed"], default="heading")
    p.add_argument("--contextual", type=_parse_onoff, default=False)
    p.add_argument("--chunk-size", type=int, default=800)
    p.add_argument("--overlap", type=int, default=200)
    p.add_argument("--model", default=os.environ.get("RAG_MODEL", "qwen3.8:27b-mlx"))
    p.add_argument("--embed-model", default="nomic-embed-text")
    p.add_argument("--judge", type=_parse_onoff, default=True, help="run LLM-as-judge")
    p.add_argument("--mock", type=_parse_onoff, default=True, help="force deterministic doubles")
    p.add_argument("--seed", type=int, default=42, help="gen-corpus seed (ignored on --mock)")
    p.add_argument("--tiers", nargs="+", choices=[
        "easy", "multi", "chunking", "distractor", "conflict", "recency", "injection"])
    p.add_argument("--stop-on-error", action="store_true")
    p.add_argument("--quiet", action="store_true", help="suppress per-case / summary output")
    p.add_argument("--verbose", action="store_true", help="loguru per-stage trace")
    p.add_argument("--show-banners", type=_parse_onoff, default=True)
    p.add_argument("--qid", default=None, help="show one question by q_id (else the first)")


def _build_parser():
    parser = argparse.ArgumentParser(prog="rag", description="RAG pipeline CLI (section 5.1)")
    sub = parser.add_subparsers(dest="command", required=True)
    gc = sub.add_parser("gen-corpus", help="generate corpus + questions.json")
    gc.add_argument("--dir", dest="outdir", default=None)
    gc.add_argument("--n-docs", type=int, default=100)
    gc.add_argument("--n-questions", type=int, default=50)
    gc.add_argument("--failure-mode-docs", default="")
    _add_common(gc)
    _add_common(sub.add_parser("build-index", help="chunk + embed + index the corpus"))
    _add_common(sub.add_parser("eval", help="run the pipeline + emit a report"))
    _add_common(sub.add_parser("show", help="print one case's evidence + verdict"))
    return parser


def main(argv=None):
    """Entry point for the `rag` console script. Returns the section-5.1 exit code."""
    configure(verbose=False, quiet=False)
    parser = _build_parser()
    ns = parser.parse_args(argv)
    ns.use_mock = ns.mock
        # E-15: --top-n < --k is bad CLI usage -> exit 2, checked before any work.
    if ns.top_n < ns.k:
        sys.stderr.write("ERROR: --top-n (" + str(ns.top_n) + ") < --k (" + str(ns.k) + "); E-15.\n")
        return 2
    try:
        if ns.command == "gen-corpus":
            ec = cmd_gen_corpus(ns)
        elif ns.command == "build-index":
            ec = cmd_build_index(ns)
        elif ns.command == "eval":
            ec = cmd_eval(ns)
        elif ns.command == "show":
            ec = cmd_show(ns)
        else:
            ec = 0
    except (ValueError, OSError) as exc:
        sys.stderr.write("LOAD_FAILURE: " + str(exc) + "\n")
        return 3
    except Exception as exc:     # noqa: BLE001 -- a live-backend fault is
        # PULL_REQUIRED (E-13 / R-19): fatal exit 4 on the real path. The
        # --mock path degrades to DEGRADED_MOCK (exit 0) so its run still
        # completes even when a backend call would 404.
        sys.stderr.write("PULL_REQUIRED: " + str(exc) + "\n")
        return 4 if not ns.mock else 0
    return ec


def main_gui(argv=None):
    """Entry point for the `rag-gui` console script (R-16, #7)."""
    try:
        ui = importlib.import_module("rag.ui")
        return int(ui.run_gui(argv))
    except ModuleNotFoundError:
        sys.stderr.write("GUI not available (PyQt5 not installed); use the `rag` CLI instead.\n")
        return 0


def main_entry():
    return main()


if __name__ == "__main__":
    raise SystemExit(main())
