---
name: md2pdf-authoring
description: Author and convert this bootcamp's Markdown+LaTeX chapters (curriculum/week1) to PDF with md2pdf.sh (pandoc + xelatex). Use when writing/editing a *.md chapter, regenerating its *.pdf, or debugging conversion warnings/errors -- covers md2pdf.sh's sed math preprocessor, the JSON-array-mangling bug, $$ math escaping, and ASCII-only diagram rules.
license: MIT
---

# md2pdf Authoring

Use this skill when creating, editing, or verifying any chapter in
`curriculum/week1/*.md` (e.g. `chapter1.md` … `chapter4.md`) and its generated
`*.pdf`, or when a conversion emits pandoc/xelatex warnings or errors.

The pipeline is `md2pdf.sh` at the repo root. It preprocesses the Markdown with
`sed`, then runs `pandoc … --pdf-engine=xelatex`. Knowing what the `sed` layer
does avoids the two recurring failure modes: **JSON-array mangling** and
**broken LaTeX math**.

## Run / verify

Always convert through the wrapper so the `.pdf` and `.md` stay in sync:

```bash
cd curriculum/week1
bash ../../md2pdf.sh --toc chapter4.md     # --toc builds a table of contents
```

A clean run prints `Success! Created 'chapter4.pdf'` and nothing else. Treat any
extra output as a warning or error to fix. The `--mermaid` flag adds
`--filter mermaid-filter` when the chapter uses mermaid diagrams.

After a change, re-verify with the checks below before committing both the `.md`
and the regenerated `.pdf` together (they must not drift).

## Root cause: the sed preprocessor

`md2pdf.sh` runs this `sed` **on the raw file, before pandoc**:

```sh
sed -e 's/^[[:space:]]*\[[[:space:]]*$/$$\n/' \
    -e 's/^[[:space:]]*\][[:space:]]*$/\n$$/'
```

That means **any line that is just `[` or `]` (optionally indented) becomes a
`$$` toggle**, regardless of context. It runs before pandoc parses fenced code
blocks, so **` ```json ` / ` ```text ` fences are NOT immune**.

### Bug 1: JSON array closing `]` renders as `$$`

A JSON array written with the closing bracket on its own line:

```json
{
   "required_sources": [
        "travel-policy-2026"
     ]
}
```

renders in the PDF with `$$` in place of `]`, because `    ]` matches the sed
rule. Fix by removing the standalone `]` -- either inline the array:

```json
{
   "required_sources": ["travel-policy-2026"]
}
```

or, for nested-object arrays, attach the bracket to the closing brace:

```json
{
   "claims": [
        { "text": "…", "source": "policy-17" } ]
}
```

Find offenders with:

```bash
grep -nE '^[[:space:]]*\][[:space:]]*$' chapter4.md   # closing ] on its own line
grep -nE '^[[:space:]]*\[[[:space:]]*$' chapter4.md    # opening [ on its own line
```

(Standalone `[`/`]` lines outside JSON are rare; the JSON closing `]` is the
one that matters.)

## Standards for LaTeX math

Match the existing chapters (chapter1–3 use display math directly; do not rely on
the `[`/`]` convention).

- **Use `$$ … $$` for math**, multi-line as the chapters do. Prefer this over a
  single-bracket `[ … ]` block even though sed also converts it -- `$$` is the
  stable, explicit convention.
- **Escape `%` as `\%`.** An unescaped `%` starts a TeX comment and truncates the
  rest of the line (e.g. `87%`, `Accuracy = 93%`, `P < 2%`).
- **Escape `$` as `\$`** inside a math block. A bare `$` toggles math mode and
  corrupts the display (e.g. `\frac{\$0.02}{0.80} = \$0.025`).
- **Separate a coefficient from a label** with `\,` and wrap the label in
  `\text{}`: `0.3\,\text{Accuracy} + 0.2\,\text{Groundedness}`.
- **Wrap bare words / labels / word-subscripts in `\text{}`**, e.g.
  `\text{HallucinationRate} = \frac{2}{10}`, `f(x) \in \mathcal{Y}_{\text{acceptable}}`.
- **Inline math uses `$ … $`**, e.g. `Change $k$.`, `$P$ = precision`.
- `\boxed{ … }` works for the key-takeaway equation.

### Fixing garbled math blocks

Corrupted blocks look like this (em-dash or `#`/`=` artifacts left from a bad
convert):

```
[
HallucinationRate =
\frac{2}{10}
================

20%
]
```

Rewrite to clean LaTeX:

```
$$
\text{HallucinationRate}
=
\frac{2}{10}
=
20\%
$$
```

Rule of thumb: a lone run of `===…=` or a leading `# ` inside a math block is a
conversion artifact -- replace it with `=` / proper `\frac{…}{…}`, then escape
`%` and `$`.

## Standards for diagrams

Diagrams in this project live in ` ```text ` fences and must render under xelatex.

- **Boxes: ASCII `+ - |` only.** Do not use Unicode box-drawing characters
  (`┌ ┐ └ ┘ │ ┬ ┴ ─ ▟`). xelatex has no reliable glyph for them and they look
  wrong.

  ```text
  +--------------+
  |   Dataset     |
  +------+-------+
          |
          ↓
  +--------------+
  |  Application  |
  +--------------+
  ```

- **Arrows: Unicode `↓` and `→` are fine** (xelatex supports them; the chapters
  use them throughout). Use them for flow between boxes.
- **Avoid characters the monospace font (`lmmono`) lacks** inside ` ```text ` /
  ` ```json ` code blocks. `∈` is the known offender: it triggers
  `Missing character: There is no ∈ (U+2208) in font [lmmono10-regular]`.
  Use the word `in` inside code fences (`currency in allowed currencies`);
  `∈` is fine **inside `$$ … $$` math**, where the math font provides it.

## Verification workflow

Run these before committing. A clean conversion + passing greps + no stray
non-ASCII means the chapter is good.

```bash
cd curriculum/week1
# 1. Convert and confirm only "Success!" is printed (no warnings/errors)
bash ../../md2pdf.sh --toc chapter4.md

# 2. No mangling of standalone brackets
grep -nE '^[[:space:]]*[\]\[]' chapter4.md || echo "brackets ok"

# 3. No Unicode box-drawing characters
grep -nE '[┌┐└┘│┬┴─▟]' chapter4.md || echo "boxes ok"

# 4. No lone [ ] math blocks (use $$ instead)
grep -nE '^[[:space:]]*\[[[:space:]]*$' chapter4.md && echo "FIX THESE" || echo "math blocks ok"

# 5. Scan for unexpected non-ASCII (review: naïve, —, ", ’, §, ↓, →, ∈ in $$ are
#    expected; anything else -- box chars, mojibake, CJK -- must be fixed)
python3 - <<'PY'
import collections
s=open("chapter4.md",encoding="utf-8").read()
for c,n in sorted(collections.Counter(x for x in s if ord(x)>127).items()):
    print(repr(c), hex(ord(c)), n)
PY
```

Expected non-ASCII in these chapters: `— – “ ” ’ § ↓ → ∈` (the last only inside
`$$` math) and the `ï` in "naïve". Anything outside that set -- especially
`┌┐└┘│┬┴─` -- is a bug.

## Common mistakes checklist

- [ ] JSON arrays don't leave `]` (or a nested `{ … } ]`) on its own line
- [ ] Percent signs escaped as `\%` inside math
- [ ] `$` escaped as `\$` inside display math
- [ ] Coefficient–label pairs use `\,` and `\text{}`
- [ ] Bare words/labels/word-subscripts wrapped in `\text{}`
- [ ] No `===…=`/leading `# ` artifacts left inside math blocks
- [ ] Diagrams use `+ - |` boxes, not Unicode box-drawing
- [ ] No `∈`/glyph-missing chars inside ` ```text ` / ` ```json ` fences
- [ ] `md2pdf.sh --toc` prints only "Success!"
- [ ] Regenerated `.pdf` committed together with the `.md`
