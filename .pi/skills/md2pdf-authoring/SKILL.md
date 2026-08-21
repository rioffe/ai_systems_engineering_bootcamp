---
name: md2pdf-authoring
description: Author and convert this bootcamp's Markdown+LaTeX chapters (any curriculum/weekNN/*.md) to PDF with md2pdf.sh (pandoc + xelatex). Use when writing/editing a *.md chapter, regenerating its *.pdf, or debugging conversion warnings/errors -- covers md2pdf.sh's sed math preprocessor, the JSON-array-mangling bug, the blank-after-`$$` pitfall, $$-math escaping, ASCII-only diagrams, and pandoc exit-code masking
license: MIT
---

# md2pdf Authoring

Use this skill when creating, editing, or verifying any chapter in
`curriculum/weekNN/*.md` (e.g. `chapter1.md` … `chapter4.md`) and its generated
`*.pdf`, or when a conversion emits pandoc/xelatex warnings or errors.

The pipeline is `md2pdf.sh` at the repo root. It preprocesses the Markdown with
`sed`, then runs `pandoc … --pdf-engine=xelatex`. Knowing what the `sed` layer
does avoids the recurring failure modes: **JSON-array mangling**, the **blank-after / blank-inside `$$`** pitfalls, and **broken LaTeX math**.

## Run / verify

Always convert through the wrapper so the `.pdf` and `.md` stay in sync:

```bash
cd curriculum/weekNN     # the week that holds the chapter
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

### Bug 2: the `[ … ]` convention injects a blank after the opening `$$`

The first sed rule `s/^[[:space:]]*\[[[:space:]]*$/$$\n/` has a `\n` *after* the
`$$`, so it **inserts a blank line after every opening `[`**. A math block written
with the `[ … ]` convention therefore becomes:

```
$$

<math content>

$$
```

Pandoc does **not** treat a `$$` that is immediately followed by a blank line as the
opening of a display-math fence. The whole equation then renders as *literal text*
and every math symbol (`\Delta`, `\sum`, `\geq`, `\neq`, `\epsilon`, `\leq`, …)
lands in the text font `lmroman`, producing a flood of
`Missing character: … in font [lmroman…]`. It also cascades into
`! Missing $ inserted` errors. Because pandoc still exits 0, the banner reads
`Success!` -- so this failure is easy to miss.

Known-good chapters (chapter1-4, 26) sidestep this by writing `$$` **natively** in
the source; the sed open-rule only matches a line that is exactly `[`/`]`, so native
`$$` fences are never touched.

**Rule: write math blocks as native `$$ … $$`. Never use the `[ … ]` convention.**
If you inherit a `[ … ]` chapter, convert its standalone `[`/`]` fence lines to `$$`
in place, leaving `* [ ]` checklist items alone:

```python
python3 - <<'PY'
out=[]
for ln in open("chapter.md").read().split("\n"):
    out.append("$$" if ln.strip() in ("[", "]") else ln)
open("chapter.md", "w").write("\n".join(out))
PY
```

Do the Bug 1 JSON-array fix *first* -- otherwise this turns a JSON closing `]` into
`$$`, too. After converting, re-run `md2pdf.sh` and the `Missing character` /
`Missing $` noise disappears. (The `==…=` runs and standalone `>` symptoms that
commonly appear *with* the blank vanish once the fence truly opens -- but tidy them
per the "Standards for LaTeX math" list below regardless.)


### Bug 3: a blank line *inside* a `$$ … $$` block makes pandoc escape the `$$`

Bug 2 is the *sed-open* variant of a deeper, general rule: **pandoc refuses to open a
display-math fence when a blank line sits anywhere between the opening and closing
`$$`.** A block can therefore carry a stray blank **even in hand-written, native-`$$`
source** -- e.g. when a separator `=` line is preceded or followed by a blank, or when
it was copied out of the `[ … ]` convention.

```
$$
A
=

\frac{b}{c}
$$
```

Here the blank line between `=` and `\frac` makes pandoc render the delimiters as
*literal* `$$` text:

```
\$\$ A =

\frac{b}{c}

\$\$
```

which drops `\frac` / `\text{…}` into text mode and cascades into
`! Missing $ inserted` (and, per Bug 2, `Missing character: … in font [lmroman…]`).
Like Bug 2 it still prints `Success!`, so it is easy to miss.

Proof (minimal): with a blank inside, pandoc escapes `$$`; without it, it renders:

```bash
printf '$$\nA\n=\n\n\\frac{b}{c}\n$$\n' > t1.md   # blank inside
printf '$$\nA\n=\\frac{b}{c}\n$$\n'     > t2.md   # no blank
pandoc t1.md --to latex    # -> \$\$ A = … \$\$    (escaped; BROKEN)
pandoc t2.md --to latex    # -> \[ A = \frac{b}{c} \]   (renders)
```

**Rule: no blank line may sit inside a `$$ … $$` block.** After converting fences, strip
any blank that falls *inside* a display-math region by toggling a flag on each line that
is exactly `$$` (a plain grep can't see block state):

```python
lines = open("chapter.md").read().split("\n")
out, in_m = [], False
for ln in lines:
    if ln.strip() == "$$":
        out.append(ln); in_m = not in_m
        continue
    if in_m and ln.strip() == "":
        continue            # drop blank line inside the fence
    out.append(ln)
open("chapter.md", "w").write("\n".join(out))
```

## Standards for LaTeX math

Match the existing chapters (chapter1–3 use display math directly; do not rely on
the `[`/`]` convention).

- **Use `$$ … $$` for math**, multi-line as the chapters do. Prefer this over a
  single-bracket `[ … ]` block even though sed also converts it -- `$$` is the
  stable, explicit convention.
- **Native `$$` is mandatory, not a style preference** -- the `[ … ]` convention
  triggers the Bug 2 blank-after-`$$`, which silently breaks every equation.
- **No blank line *inside* a `$$ … $$` block.** A blank between the delimiters makes
  pandoc escape the `$$` to literal `$$` text, after which the equation breaks
  (`! Missing $ inserted` / `Missing character`). This is the general form of the
  Bug 2 open-line blank; strip it with the toggle-flag pass, not by eye. This is *not
  catchable by a single grep* -- you must track the open/close `$$` state.
- **`{cases}` blocks must end in a brace and use `\\` for row separators.**
  Write `\boxed{ \begin{cases} A \\ B \\ C \end{cases} }` so the display closes on
  a `}`; a lone trailing `\` on a row is a control-space / line-break, *not* a row
  separator.
- **No `==`-runs and no standalone `>` inside a fence.** A run of `===…=` typesets
  as a literal string of equals; a line that is only `>` becomes a Markdown
  blockquote. Use one `=`, and rank on one line: `A > B > C`.
- **Reference displayed quantities inline.** A prose sentence like
   `… or (T_{p99}) where appropriate.` must be inlined as
   `… or $T_{p99}$ where appropriate.` -- a parenthesized `(…)` is never math.
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
cd curriculum/weekNN     # the week that holds the chapter
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

## Debugging a "Success but wrong" conversion

The trickiest part is that several failures still print `Success!` because pandoc
exits 0; the real signal lives in **stderr** as `Missing $` or
`Missing character: … in font [lmroman…]`.

**The exit code is easy to mask -- do not fall for either trap:**

- **`-o /dev/null` masks the xelatex pass.** `pandoc … -o /dev/null` returns success
  even while xelatex emits `Missing $`. Always convert to a **real** `.pdf` path and
  read pandoc's stderr.
- **A pipe masks pandoc's exit.** `pandoc … 2>&1 | grep …` reports *grep's* exit,
  not pandoc's. Capture stderr to a file and grep that file, or run pandoc alone and
  read stderr.

**Localize the first broken block by binary-searching prefixes** of the
*sed-processed* file (what pandoc actually consumes), checking the **real** exit
code until the first `n` that fails -- that `n` is the first offending math block:

```bash
sed -e 's/^[[:space:]]*\[[[:space:]]*$/$$\n/' \
     -e 's/^[[:space:]]*\][[:space:]]*$/\n$$/' chapter.md > /tmp/proc.md
for n in $(seq 50 50 600); do
  head -n "$n" /tmp/proc.md > /tmp/s.md
  pandoc /tmp/s.md --pdf-engine=xelatex -o /tmp/s.pdf 2>/dev/null || { echo "first break at line $n"; break; }
done
sed -n "$((n-8)),${n}p" /tmp/proc.md    # inspect the failing region
```

The `l.<n>` in the xelatex log points at a line in pandoc's generated `.tex`, *not*
`chapter.md`; inspect the sed-processed prefix above to map back to the source.


## Common mistakes checklist

- [ ] Math blocks are native `$$ … $$` in source, not the `[ … ]` convention
     (Bug 2: `[` injects a blank after the opening `$$`, silently breaking every
     equation -- symptoms: `Missing character: … in font [lmroman…]`, or cascaded
     `! Missing $ inserted`; the run still prints `Success!`)
- [ ] No blank line *inside* a `$$` block (Bug 3: a blank between the delimiters makes
      pandoc escape `$$` to literal `$$`, then `! Missing $ inserted`; strip it with the
      toggle-flag script, not by eye -- it isn't catchable by a single grep)
- [ ] No `===…=` run or a line that is just `>` inside a math fence (use one `=` and
       a one-line `A > B > C`)
- [ ] `{cases}` fences end in `}` (wrap as `\boxed{…}`); rows separate with `\\`,
       not a lone trailing `\`
- [ ] Convert to a **real** `.pdf` and read stderr -- never trust a "Success!" from a
       piped / `-o /dev/null` pandoc run; check for `Missing $` /
        `Missing character [lmroman]`

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
