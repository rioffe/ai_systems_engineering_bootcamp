#!/bin/bash
# build-book.sh -- assemble ALL canonical chapters into one "book" PDF.
#
# It concatenates curriculum/week*/chapter<N>.md (in chapter-number order) into a
# single Markdown source, applies the SAME math preprocessor as md2pdf.sh, then
# runs pandoc once so the whole book shares one master table of contents, a
# title page, and "book" document class (# Chapter N -> \chapter, new page each).
#
#   tools/build-book.sh                   -> book.pdf at repo root
#   tools/build-book.sh out.pdf           -> custom output path
#   TITLE="..." AUTHOR="..." tools/build-book.sh
#   INTRO=0 tools/build-book.sh             -> omit the Introduction front matter
#                                             (default: on)
#
# Only the chapters that embed mermaid diagrams (currently ch1) need a Chrome/
# Chromium for the mermaid-filter; one is auto-detected (same as md2pdf.sh) and is
# overridable via PUPPETEER_EXECUTABLE_PATH.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CURRIC="curriculum"
OUT="${1:-$ROOT/book.pdf}"
TITLE="${TITLE:-AI Systems Engineering: A Practical Bootcamp}"
AUTHOR="${AUTHOR:-}"
DATE="${DATE:-$(date +%Y)}"

# ---- ordered chapter source list (skip day*.md and *_vN drafts) --------------
chapters="$(
        python3 - "$CURRIC" <<'PY'
import os, sys, re
cur = sys.argv[1]
fs = []
for week in os.listdir(cur):
    d = os.path.join(cur, week)
    if not os.path.isdir(d):
        continue
    for name in os.listdir(d):
        m = re.fullmatch(r"chapter(\d+)\.md", name)
        if m:
            fs.append((int(m.group(1)), os.path.join(cur, week, name)))
for _, p in sorted(fs):
    print(p)
PY
)"

if [ -z "$chapters" ]; then
        echo "build-book.sh: no chapter*.md files found under $CURRIC" >&2
        exit 1
fi

# ---- optionally prepend the book's Introduction as front matter -----------
# The Introduction (curriculum/introduction.md) is front matter: its own
# "# Introduction" chapter -- landing at the top of the master "Contents" list and
# opening on its own page (book class -> \chapter).  Opt out with INTRO=0.
intro="$CURRIC/introduction.md"
if [ "${INTRO:-1}" != 0 ] && [ -f "$intro" ]; then
        chapters="$intro"$'\n'"$chapters"
        echo "build-book: including Introduction front matter"
fi

total="$(printf '%s\n' "$chapters" | grep -c .)"

# ---- assemble the combined source -------------------------------------------
SRC="$(mktemp /tmp/build-book-src.XXXXXX.md)"
PROCF="$(mktemp /tmp/build-book-proc.XXXXXX.md)"
trap 'rm -f "$SRC" "$PROCF"' EXIT

n=0
while IFS= read -r p; do
    [ -z "$p" ] && continue
    [ "$n" -gt 0 ] && printf '\n\\newpage\n\n' >> "$SRC"     # blank page break between chapters
    cat -- "$p" >> "$SRC"
    n=$((n + 1))
    printf 'merge: %-30s (%d of %d)\n' "$(basename "$p")" "$n" "$total"
done <<< "$chapters"

# ---- apply the SAME [ / ] -> $$ math preprocessor as md2pdf.sh --------------
sed -e 's/^[[:space:]]*\[[[:space:]]*$/$$\n/' \
    -e 's/^[[:space:]]*\][[:space:]]*$/\n$$/' \
        "$SRC" > "$PROCF"

# ---- decide on the mermaid-filter, then auto-detect a Chrome/Chromium -------
mermaid_args=""
if grep -q '^```mermaid' "$SRC"; then
    if [ -z "${PUPPETEER_EXECUTABLE_PATH:-}" ]; then
        for cand in \
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
            "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary" \
            "/Applications/Chromium.app/Contents/MacOS/Chromium" \
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"; do
            [ -x "$cand" ] && { PUPPETEER_EXECUTABLE_PATH="$cand"; break; }
        done
        [ -n "${PUPPETEER_EXECUTABLE_PATH:-}" ] || for c in \
            google-chrome google-chrome-stable chromium chromium-browser; do
            bin="$(command -v "$c" 2>/dev/null || true)"
            [ -n "$bin" ] && { PUPPETEER_EXECUTABLE_PATH="$bin"; break; }
        done
    fi
    if [ -n "${PUPPETEER_EXECUTABLE_PATH:-}" ]; then
        export PUPPETEER_EXECUTABLE_PATH
        echo "build-book: mermaid browser: $PUPPETEER_EXECUTABLE_PATH"
    else
        echo "build-book: WARNING: no Chrome/Chromium found; mermaid diagrams may fail." >&2
    fi
    mermaid_args="--filter mermaid-filter"
fi

echo "build-book: assembled $n chapters -> building $OUT"

# One title / master TOC for the whole book. Book document class makes each
# "# Chapter N" a \chapter (automatic new page). No --number-sections because the
# chapter titles already carry "Chapter N". $mermaid_args is a pre-split arg list
# (--filter mermaid-filter) and is intentionally expanded unquoted.
# shellcheck disable=SC2086
pandoc "$PROCF" \
    --toc --toc-depth=2 \
    --pdf-engine=xelatex \
    --variable documentclass=book \
    --variable colorlinks=true \
    --metadata "title=$TITLE" \
    --metadata "author=$AUTHOR" \
    --metadata "date=$DATE" \
    $mermaid_args \
    -o "$OUT" && echo "Success! Created '$OUT'."
