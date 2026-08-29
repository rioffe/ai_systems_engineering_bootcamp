import re
import sys
import ast
from pathlib import Path

# reindent.py — normalize leading whitespace to a nearest-multiple-of-4 grid.
#
# Improvements over the v1 tool (both are strict superset changes):
#   1. Comment / docstring-open / docstring-close lines are now snapped too.
#      v1 left comment lines un-snapped; Python ignores comment indentation so
#      that was only ugly, not fatal, but a 5/6-space comment inside a 4-space
#      block reads wrong and drifts. A continuation `)` inside brackets is
#      likewise snapped for consistency.
#   2. A parse SAFETY GUARD: the reindented OUTPUT is validated with ast.parse
#      in-memory and, if it does not parse, the file is left UNCHANGED. v1
#      wrote unconditionally and could emit broken indentation. Per-line
#      nearest-4 cannot model true nesting, so the guard is what makes the
#      transform safe to run over many files.
#
# Interior triple-quoted string content and blank lines stay byte-identical.


def snap(line: str) -> str:
    """Round a line's leading spaces to the nearest multiple of 4.

    k in {1,2,3} with k>0 collapses to column 0 (a sub-4 indent is never a
    body indent). Lines already on the grid are unchanged (idempotent).
    """
    m = re.match(r"^( +)(.*)$", line)
    if not m:
        return line
    spaces, rest = m.group(1), m.group(2)
    k = len(spaces)
    nearest = round(k / 4.0) * 4
    if nearest < 4 and k > 0:
        nearest = 0
    return " " * nearest + rest


def transform(src: str) -> str:
    """Apply the nearest-multiple-of-4 snap to every snapped line."""
    out: list[str] = []
    in_triple = False
    for raw in src.split("\n"):
        count = raw.count('"""')
        is_opening = (not in_triple) and (count % 2 == 1)
        is_closing = in_triple and (count % 2 == 1)
        is_interior = in_triple and (not is_closing)
        if is_interior:
            out.append(raw)  # interior string content: cosmetic
        elif raw.lstrip(" ") == "":
            out.append(raw)  # blank line: byte-identical
        else:
            out.append(snap(raw))  # stmt / comment / docstring open|close
        if is_opening:
            in_triple = True
        if is_closing:
            in_triple = False
    return "\n".join(out)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: reindent.py <path>", file=sys.stderr)
        return 2
    path: str = argv[1]
    p = Path(path)
    try:
        src = p.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"reindent: cannot read {path}: {exc}", file=sys.stderr)
        return 2

    new = transform(src)

    # Safety guard: never write a file that does not parse.
    try:
        ast.parse(new, path)
    except SyntaxError as exc:
        print(
            f"reindent: SKIPPED {path} — reindented output would not parse "
            f"({exc.msg} @ line {exc.lineno}); file left untouched.",
            file=sys.stderr,
        )
        return 1

    if new == src:
        print(f"reindented {path} (idempotent)")
    else:
        try:
            p.write_text(new, encoding="utf-8")
        except OSError as exc:
            print(f"reindent: cannot write {path}: {exc}", file=sys.stderr)
            return 2
        print(f"reindented {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
