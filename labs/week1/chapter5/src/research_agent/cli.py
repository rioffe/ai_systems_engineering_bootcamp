"""research-agent command line interface."""
# pyright: reportMissingImports=false
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import load_budgets
from .drills import DRILLS, run_drill
from .report import load_trace, render_trace, write_drill_report, write_trace
from .tools import build_registry

ROOT = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research-agent")
    parser.add_argument("--self-check", action="store_true")
    sub = parser.add_subparsers(dest="command")
    run = sub.add_parser("run")
    run.add_argument("--question", required=True)
    run.add_argument("--out", required=True)
    run.add_argument("--corpus", default=str(ROOT / "corpus"))
    run.add_argument("--budgets")
    run.add_argument("--mock", action="store_true")
    run.add_argument("--real", action="store_true")
    drill = sub.add_parser("drill")
    drill.add_argument("--name", choices=sorted(DRILLS), required=True)
    drill.add_argument("--out", required=True)
    drill.add_argument("--budgets")
    trace = sub.add_parser("trace")
    trace.add_argument("path")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if args.self_check:
            root = Path(__file__).parent
            forbidden = ("import " + "httpx", "import " + "ollama", "from " + "ollama")
            for path in root.glob("*.py"):
                if path.name != "policy.py" and any(item in path.read_text() for item in forbidden):
                    return 1
            return 0
        if args.command == "run":
            registry = build_registry(args.corpus)
            budgets = load_budgets(args.budgets)
            from .policy import MockPolicy, resolve_policy
            from .runtime import AgentRuntime
            policy, availability, banner, exit_code = resolve_policy(args.real and not args.mock)
            artifact = AgentRuntime(policy if args.real else MockPolicy(), registry, budgets).run(args.question)
            artifact["availability"] = availability
            if banner:
                print(banner, file=sys.stderr)
            write_trace(args.out, artifact)
            return exit_code
        if args.command == "drill":
            report = run_drill(args.name, load_budgets(args.budgets) if args.budgets else None)
            write_drill_report(args.out, report)
            return 0 if report["verdict"]["pass"] else 1
        if args.command == "trace":
            print(render_trace(load_trace(args.path)))
            return 0
        return 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
