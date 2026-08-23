#!/bin/bash
# build-book-localtoc.sh -- assemble ALL canonical chapters into one "book" PDF
# with a TWO-LEVEL, clickable, paginated table of contents.  This is the
# alternative to build-book.sh (single deep master TOC via --toc-depth=2, ~30pp).
#
#   Level 1 (master): a front-matter "Contents" listing ONLY the chapters
#          (# "Chapter N: ..." -> \chapter).  pandoc --toc --toc-depth=1.
#   Level 2 (local):  every chapter opens with its OWN "Contents" page -- a
#       per-chapter table of contents built by the etoc package, listing that
#       chapter's ## sections and ### subsections, WITH page numbers and
#       clickable (hyperref) entries.
#
# Layout produced for each chapter:
#       page 1: the chapter title, alone
#       page 2: the chapter's local "Contents" (this chapter's sections)
#       page 3: the start of the chapter body
# i.e. the title is isolated on its own page, and the local TOC is on its own
# page, separated from the body by a page break.
#
#   tools/build-book-localtoc.sh                  -> book-local.pdf at repo root
#   tools/build-book-localtoc.sh out.pdf          -> custom output path
#   TITLE="..." AUTHOR="..." tools/build-book-localtoc.sh
#   LOCAL_DEPTH=2 tools/build-book-localtoc.sh    -> sections only (default 3)
#
#   INTRO=0 tools/build-book-localtoc.sh            -> omit the Introduction front
#                                                    matter (default: on)
#
# Why latexmk, not xelatex: a per-chapter \tableofcontents needs several LaTeX
# passes for the cross-references (page numbers) to stabilise.  pandoc runs its
# pdf engine only once, so we use the latexmk engine -- which iterates to a fixed
# point -- via `--pdf-engine=latexmk`.  latexmk still runs inside pandoc's work
# dir, so the mermaid-filter images resolve exactly as in md2pdf.sh / build-book.sh.
#
# Same math preprocessor ([ ... ] -> $$ ... $$) and mermaid handling as
# md2pdf.sh / build-book.sh.  Only the chapters that embed mermaid diagrams
# (currently ch1) need a Chrome/Chromium.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CURRIC="curriculum"
OUT="${1:-$ROOT/book-local.pdf}"
TITLE="${TITLE:-AI Systems Engineering: A Practical Bootcamp}"
AUTHOR="${AUTHOR:-}"
DATE="${DATE:-$(date +%Y)}"

# Depth of the per-chapter local TOC: 2 = sections only; 3 (default) =
# sections + subsections (###).  Override via LOCAL_DEPTH env.
LOCAL_DEPTH="${LOCAL_DEPTH:-3}"

# ---- ordered chapter source list (skip day*.md and *_vN drafts) -----------
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
        echo "build-book-localtoc: no chapter*.md files found under $CURRIC" >&2
        exit 1
fi

# ---- optionally prepend the book's Introduction as front matter -----------
# The Introduction (curriculum/introduction.md) is assembled at the top of the
# document -- its own title page, then its body -- and it lands top-level in the
# master "Contents" list.  Unlike real chapters, however, it is front matter: it
# gets NO per-chapter local "Contents" page (even though it has a ## subsection).
# Opt out of the Introduction entirely with INTRO=0.
intro="$CURRIC/introduction.md"
NOLOCAL=""
license_md="$CURRIC/license.md"
# The License page has no ## / ### subheadings, so it earns no per-chapter
# local "Contents" page on its own. Prepend it first; intro is prepended next,
# so the final order is intro -> License -> chapters.
if [ "${LICENSE:-1}" != 0 ] && [ -f "$license_md" ]; then
        chapters="$license_md"$'\n'"$chapters"
        echo "build-book-localtoc: including License front matter"
fi
if [ "${INTRO:-1}" != 0 ] && [ -f "$intro" ]; then
        chapters="$intro"$'\n'"$chapters"
        NOLOCAL="$intro"
fi

total="$(printf '%s\n' "$chapters" | grep -c .)"

# ---- assemble the combined source, injecting a local TOC per chapter -------
SRC="$(mktemp /tmp/bblt-src.XXXXXX.md)"
PROC="${SRC}.proc.md"
LIST="$(mktemp /tmp/bblt-list.XXXXXX.txt)"
ASMPY="$(mktemp /tmp/bblt-asm.XXXXXX.py)"
HEADER="$(mktemp /tmp/bblt-header.XXXXXX.tex)"
trap 'rm -f "$SRC" "$PROC" "$LIST" "$ASMPY" "$HEADER"' EXIT

# LaTeX preamble for the local TOC: load hyperref FIRST so etoc can attach
# clickable links, then etoc.  pandoc adds "bookmark" + \hypersetup after this.
printf '%s\n%s\n' \
     '\usepackage[hidelinks=true]{hyperref}' \
     '\usepackage{etoc}' > "$HEADER"

# The assembler reads the ordered chapter paths from LIST (argv[1]) and the local
# TOC depth from argv[2].  For each chapter it injects -- right after the
# chapter's "# Chapter N" H1, and only when the chapter has ## /### subsections --
# a raw LaTeX block:
#    \newpage                                   -> local TOC on its own page
#    {\etocsettocdepth{N}\localtableofcontents} -> etoc prints this chapter's
#                          local TOC (sections/subsections, WITH page numbers
#                          and clickable links, because hyperref is loaded first)
#    \newpage                                   -> chapter body starts fresh
# No heading parsing/escaping is needed: etoc reads the real \section titles.
printf '%s\n' "$chapters" > "$LIST"
cat > "$ASMPY" <<'PY'
import re, sys

LIST, DEPTH = sys.argv[1], sys.argv[2]
NOLOCAL = sys.argv[3] if len(sys.argv) > 3 else ""
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
SUBSECTION = re.compile(r"^#{2,4}\s+\S")      # ## .. #### => a local-TOC entry
BLOCK = (
      "```{=latex}\n"
    r"\newpage" + "\n"
    r"{\etocsettocdepth{" + DEPTH + r"}\localtableofcontents}" + "\n"
    r"\newpage" + "\n"
      "```"
)

paths = [l.strip() for l in open(LIST, encoding="utf-8") if l.strip()]
out = []
for n, path in enumerate(paths):
    with open(path, encoding="utf-8", errors="replace") as f:
        src = f.read().splitlines()

     # a chapter earns a local TOC page only if it has ## /### subsections
    is_nolocal = NOLOCAL != "" and path == NOLOCAL
    has_subs = any(SUBSECTION.match(l) for l in src) and not is_nolocal

     # locate the chapter's first H1 (# "Chapter N: ...")
    h1 = 0
    for i, ln in enumerate(src):
        m = HEADING.match(ln)
        if m and len(m.group(1)) == 1:
            h1 = i
            break

    chunk = list(src[:h1 + 1])
    if has_subs:
        chunk += ["", BLOCK, ""]
    chunk += src[h1 + 1:]

    text = "\n".join(chunk)
     # chapters are separated by a blank page break
    out.append(text if n == 0 else r"\newpage" + "\n" + text)

sys.stdout.write("\n\n".join(out) + "\n")
PY

python3 "$ASMPY" "$LIST" "$LOCAL_DEPTH" "$NOLOCAL" > "$SRC"

if [ ! -s "$SRC" ]; then
        echo "build-book-localtoc: assembled source is empty" >&2
        exit 1
fi

echo "build-book-localtoc: assembled $total chapters ($(wc -l < "$SRC") source lines)"

# ---- apply the SAME [ / ] -> $$ math preprocessor as md2pdf.sh -----------
sed -e 's/^[[:space:]]*\[[[:space:]]*$/$$\n/' \
    -e 's/^[[:space:]]*\][[:space:]]*$/\n$$/' \
     "$SRC" > "$PROC"

# ---- decide on the mermaid-filter, then auto-detect a Chrome/Chromium -----
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
        echo "build-book-localtoc: mermaid browser: $PUPPETEER_EXECUTABLE_PATH"
    else
        echo "build-book-localtoc: WARNING: no Chrome/Chromium found; mermaid diagrams may fail." >&2
    fi
    mermaid_args="--filter mermaid-filter"
fi

echo "build-book-localtoc: building $OUT"
echo "build-book-localtoc: master TOC depth=1 (chapters); per-chapter local TOC depth=$LOCAL_DEPTH (etoc, linked; multi-pass via latexmk)"

#   --toc --toc-depth=1        -> master "Contents" lists chapters only.
# Per-chapter local TOCs are injected as raw etoc blocks (see above); latexmk
# iterates xelatex to a fixed point so the page numbers are correct.
# $mermaid_args is a pre-split arg list (--filter mermaid-filter), expanded
# unquoted on purpose.
# shellcheck disable=SC2086
pandoc "$PROC" \
     --toc --toc-depth=1 \
     --pdf-engine=latexmk \
     --pdf-engine-opt="-xelatex" \
     --pdf-engine-opt="-interaction=nonstopmode" \
     --include-in-header="$HEADER" \
     --variable documentclass=book \
     --variable colorlinks=true \
     --metadata "title=$TITLE" \
     --metadata "author=$AUTHOR" \
     --metadata "date=$DATE" \
     $mermaid_args \
     --output "$OUT" && echo "Success! Created '$OUT'."
