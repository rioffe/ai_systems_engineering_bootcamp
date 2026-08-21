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

A clean run ends with `Success! Created 'chapter4.pdf'`. Treat any extra output
*after the banner* as a warning or error to fix. The `--mermaid` flag adds
`--filter mermaid-filter` when the chapter uses mermaid diagrams.

Note: `md2pdf.sh` prints banner lines on *every* run -- `Arg: ...`,
`Processing '...'...`, and `Converting ...`. Those are not warnings. To see only
the signal, filter them out:

```bash
bash ../../md2pdf.sh --toc chapter4.md 2>&1 | grep -viE '^Arg: |^Processing|^Converting' || echo "no output -- clean"
```

The end state -- only that banner/Success and nothing more -- means the chapter
converted without pandoc/xelatex complaints.

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
- **Prose `\(var\)` is NOT math.** A drafted chapter may denote a variable as
  gloss-parenthesized `(...)`, e.g. `where (x) is the prompt, (f_\theta) is the
  model`. Pandoc (default extensions) only treats `$…$`/`$$…$$` as math, so a
  bare `(f_\theta)` renders the literal characters `\theta` -- garbled output that
  compiles with **no warning**. Convert every prose `\(var\)` whose token carries
  math (subscripts, `\_`, `\theta`, Greek letters, or a named metric with a
  subscript like `T_{p99}`) to inline `$…$`. (Ordinary
  English parentheticals and code function calls like `F(s_t)` are not offenders.)

      `` where (x) is the prompt, (f_\theta) is the model `` =>
      `` where $x$ is the prompt, $f_\theta$ is the model ``

      A frequent spot to miss it: a short prose sentence that references
      back to a quantity just displayed in a `$$ … $$` block. E.g. a
      display equation for `T_{p95}` followed by `or (T_{p99}) where
      appropriate.` -- that `(T_{p99})` means "the p99 latency" and
      must be inlined:

      `` ...or (T_{p99}) where appropriate. `` =>
      `` ...or $T_{p99}$ where appropriate. ``

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
  use them throughout). Use them for flow between boxes. The large **triangle
  arrows `▲` `▼` are NOT in the font** -- use ASCII `^`/`v` (`▲` => `^`, `▼` => `v`;
  `↑` is unreliable too, so prefer `^` for a generic up-arrow).
- **Avoid characters the monospace font (`lmmono`) lacks** inside ` ```text ` /
    ` ```json ` code blocks. Fenced code uses a monospace font that has no glyph for
   math symbols, so treat any such glyph placed in a code fence as risky and use a
   plain-ASCII equivalent instead. Known offenders:
      `∈` (U+2208, triggers `Missing character: ... in font [lmmono10-regular]`),
    `×` (U+00D7, as in `3× performance`), `≤`/`≥` (=> `<=`/`>=`), `≈` (=> `~`).
   Example: `currency in allowed currencies`, `3x performance`.
   These symbols are fine inside `$$ ... $$` math, where the math font provides them.

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

Expected non-ASCII in these chapters: `— – “ ” ’ § ↓ →` and the `ï` in "naïve"
(`∈` may appear but only inside `$$` math). Anything outside that set -- box
characters `┌┐└┘│┬┴─`, triangle arrows `▲▼`, or `×`/`≈`/`≤`/`≥` inside a code fence --
is a bug to fix.

## Common mistakes checklist

- [ ] JSON arrays don't leave `]` (or a nested `{ … } ]`) on its own line
   (an empty array on one line, `[]`, is **safe** -- it matches neither the
   open-`[` nor close-`]` sed rule, so don't "fix" it)
- [ ] Prose `\(var\)` / `\(f_\theta\)` math notation converted to inline `$…$`
- [ ] No triangle arrows `▲ ▼` (or `↑`) in ` ```text ` diagrams -- use `^` / `v`
- [ ] No `×` / `≈` / `≤` / `≥` / `∈` glyphs inside ` ```text ` / ` ```json ` fences
- [ ] Percent signs escaped as `\%` inside math
- [ ] `$` escaped as `\$` inside display math
- [ ] Coefficient–label pairs use `\,` and `\text{}`
- [ ] Bare words/labels/word-subscripts wrapped in `\text{}`
- [ ] No `===…=`/leading `# ` artifacts left inside math blocks
- [ ] Diagrams use `+ - |` boxes, not Unicode box-drawing
- [ ] No `∈`/glyph-missing chars inside ` ```text ` / ` ```json ` fences
- [ ] `md2pdf.sh --toc` prints only "Success!"
- [ ] Regenerated `.pdf` committed together with the `.md`
