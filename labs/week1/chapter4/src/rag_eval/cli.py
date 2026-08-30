"""Command line interface for rag-eval."""
# pyright: reportMissingImports=false

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .dataset import load_dataset, validate_dataset
from .report import (
    load_artifact,
    render_compare_table,
    write_compare_report,
    write_eval_artifact,
    write_gate_report,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rag-eval")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check"); check.add_argument("--dataset", required=True); check.add_argument("--strict", action="store_true"); check.add_argument("--out", default="dataset_report.json")
    run = sub.add_parser("run"); run.add_argument("--dataset", required=True); run.add_argument("--corpus", required=True); run.add_argument("--out", required=True); run.add_argument("--mock", action="store_true"); run.add_argument("--top-k", type=int, default=5)
    compare = sub.add_parser("compare"); compare.add_argument("--baseline", required=True); compare.add_argument("--current", required=True); compare.add_argument("--out", default="compare_report.json"); compare.add_argument("--force", action="store_true")
    gates = sub.add_parser("gates"); gates.add_argument("--baseline", required=True); gates.add_argument("--current", required=True); gates.add_argument("--config", required=True); gates.add_argument("--out", default="gate_report.json")
    judge = sub.add_parser("judge-check"); judge.add_argument("--labels", required=True); judge.add_argument("--eval", required=True); judge.add_argument("--out", default="judge_check_report.json")
    new_case = sub.add_parser("new-case"); new_case.add_argument("--trace", required=True); new_case.add_argument("--case-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if args.command == "check":
            dataset = load_dataset(args.dataset, validate=False)
            violations = validate_dataset(dataset, strict=args.strict)
            Path(args.out).write_text(json.dumps({"ok": not violations, "violations": violations}, sort_keys=True) + "\n")
            return 3 if violations else 0
        if args.command == "run":
            dataset = load_dataset(args.dataset, validate=False)
            violations = validate_dataset(dataset)
            if violations:
                return 3
            from .pipeline import run_dataset
            artifact = run_dataset(dataset, args.corpus, query_flags={"top_k": args.top_k})
            write_eval_artifact(args.out, artifact)
            return 0
        if args.command == "compare":
            from .compare import compare_artifacts
            report = compare_artifacts(load_artifact(args.baseline, "eval", args.force), load_artifact(args.current, "eval", args.force), force=args.force)
            write_compare_report(args.out, report)
            print(render_compare_table(report))
            return 0
        if args.command == "gates":
            from .compare import compare_artifacts
            from .gates import evaluate_gates, gate_exit_code
            from .schema import load_yaml
            report = compare_artifacts(load_artifact(args.baseline, "eval"), load_artifact(args.current, "eval"))
            result = evaluate_gates(report, load_yaml(args.config, "gates"))
            write_gate_report(args.out, result)
            return gate_exit_code(result)
        if args.command == "judge-check":
            from .judge_check import judge_check
            labels = json.loads(Path(args.labels).read_text())
            result = judge_check(load_artifact(args.eval, "eval"), labels)
            write_gate_report(args.out, result)
            return 3 if result["status"] == "NO_LABELS" else 0
        if args.command == "new-case":
            from .aoe import load_trace
            from .new_case import scaffold_case
            print(json.dumps(scaffold_case(load_trace(args.trace), args.case_id), sort_keys=True))
            return 0
        return 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
