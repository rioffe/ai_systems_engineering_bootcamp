import sys, re

path = sys.argv[1]
lines = open(path, encoding="utf-8").read().split("\n")
TQ = '"""'

def snap(line):
    m = re.match(r"^( +)(.*)$", line)
    if not m:
        return line
    spaces, rest = m.group(1), m.group(2)
    k = len(spaces)
    nearest = round(k / 4.0) * 4
    if nearest < 4 and k > 0:
        nearest = 0
    return " " * nearest + rest

out = []
in_triple = False
for raw in lines:
    count = raw.count(TQ)
    is_opening = (not in_triple) and (count % 2 == 1)
    is_closing = in_triple and (count % 2 == 1)
    is_interior = in_triple and (not is_closing)
    if is_interior:
        out.append(raw)   # interior string content: cosmetic, leave untouched
        continue
    stripped = raw.lstrip(" ")
    if stripped == "" or stripped.startswith("#"):
        out.append(raw)   # blank/comment line: Python-irrelevant indent
    else:
        out.append(snap(raw))   # statement line (incl. docstring open/close): snap
    if is_opening:
        in_triple = True
    if is_closing:
        in_triple = False
open(path, "w", encoding="utf-8").write("\n".join(out))
print("reindented", path)
