---
name: spec-build
description: Implement a provided SPEC.md for a bootcamp lab (labs/weekNN/chapterNN or any source of truth named SPEC.md) using test-driven development, then make the project's README.md reflect the built reality, then re-read SPEC.md and review every produced artifact for conformance. Use when asked to "build the spec", "implement SPEC.md", "make this spec real", or after spec-writing/spec-review produce a Level-2/3 spec. Pairs with spec-writing (authoring the spec), spec-review (auditing it, yielding SPEC_REVIEW_REPORT.md + F-xxx findings and a P0/P1/P2 remediation plan), md2pdf-authoring (rendering .pdf), and the TDD/debug/verify superpowers skills. Encodes the red-green-refactor loop over the spec's §9 test groups, the "implement everything unless told otherwise" default, README-sync, and the final spec-conformance pass.
license: MIT
---

# spec-build

Turn a `SPEC.md` into a working, tested, documented implementation. This is the **implementer
companion** to `spec-writing` (which authors the spec) and `spec-review` (which audits it). The
spec is the **source of truth**; the build must satisfy it, and the README must report what was
actually built.

The build has three phases and you do not skip any:

1. **Build (TDD).** Implement the spec test-first using `superpowers:test-driven-development`
   — write the failing test from §9, watch it fail for the right reason, write the minimal code,
   watch it pass, refactor. Commit intermediate work.
2. **Document.** When the suite is green, make `README.md` reflect the implemented system
   (not the intended one).
3. **Prove conformance.** Re-read `SPEC.md`, then review *every* produced artifact against it
   and produce a conformance report. Do not call the work done until this pass is clean.

**The default is to implement everything in the spec.** Every requirement, contract, invariant,
edge case, and acceptance test in the spec gets realized — unless the user explicitly told you
to scope something out. A `MAY`/`SHOULD`/optional (`O-n`) item is still implemented to the point
the spec demands; "optional" means gated/behind a flag, not omitted. If you decide *not* to build
an in-scope item, say so, show which spec ID it was, and get the user's approval first.

## When to use

- "implement SPEC.md" / "build the <X> spec" / "make `<SPEC.md>` real"
- a lab exists with a `SPEC.md` but no `src/` implementation, or only a partial one
- after `spec-review` returns `IMPLEMENT_READY` (or "READY WITH MINOR FIXES") — start building
- "finish this chapter lab" where the spec is written but the code isn't

Do **not** start building while `spec-review` returned `NOT READY` or left unresolved **P0**
findings. Fold P0 (blocking) and P1 (important) findings into the spec / acceptance suite first;
P2 (improvement) MAY be deferred. See *Phase 0* below.

## The lab layout you are working in

This bootcamp's `labs/weekNN/chapterNN/` labs (e.g. `labs/week1/chapter4/`) use a fixed shape.
Match it; for a non-bootcamp spec, adapt — but keep the three artifacts below always:

| Artifact | Purpose | Must track |
| --- | --- | --- |
| `SPEC.md` | Source of truth | unchanged during build; only `fix()` after a found drift |
| `src/<pkg>/` | the implementation | every §2 requirement, §4 contract, §6 invariant |
| `tests/` | the §9 acceptance suite | every T-nn id, one group per §9 subsection |
| `schemas/`, `documents/`, `corpus/` | data/artifacts the spec pins | the §4 contract / §10 deps |
| `pyproject.toml`, `uv.lock` | env + CLI entry points | the §5.1 CLI surface, §10 deps |
| `README.md` | the built reality | Setup / Commands / Artifacts / Verification / layout |

Default stack here is **Python 3.12 + `uv`**: `uv sync --extra dev` to install; the test and
lint commands are:

```bash
cd labs/weekNN/chapterNN
uv run python -m pytest tests -q        # the §9 acceptance suite
uv run ruff check src tests             # lint
uv run <cli> --self-check               # when the spec pins a --self-check boundary (§5.1)
```

For another stack substitute the equivalent "write a test → run it → run all → lint", but the
three-phase shape below is identical.

---

# Phase 0 — Commit to the spec before writing a line

Do this once, up front. It is the plan that keeps TDD honest.

### 0.1 Read the spec fully, end to end

Read the whole `SPEC.md` in one pass **before** touching code — do not skim. Build a mental
model of the §0 intent, the §3 state flow, and the deterministic ↔ optional boundary. If a
`SPEC_REVIEW_REPORT.md` exists, read its **Remediation Plan** (§20: P0/P1/P2) and **Final
Verdict** (§21) and its §4 detailed findings (`F-00x`, with severity). If the verdict is
`NOT READY`, stop and route through `spec-review` / `spec-writing` first.

### 0.2 Extract the build list from the spec's own IDs

The spec already numbers everything. Turn it into a checklist so nothing is silently dropped.
For each family collect the open items and their owner:

- **R-nn** requirements (§2) → the behaviors to build.
- **C-nn** contracts (§4) → the interfaces, data shapes, module boundaries to honor.
- **I-nn** invariants (§6) → global properties every implementation must keep (e.g. I-001
  zero-/negative-denominator fallbacks; byte-determinism; the §5.3 verbosity invariant).
- **K-nn** constraints (§7) → measurable limits (exit codes `2`/`3`, thresholds, `--strict`).
- **E-nn** edge cases (§8) → the failure semantics you must encode, not discover later.
- **T-nn** tests (§9) → **one failing test first** for each, grouped by §9 subsection.
- **§11 traceability matrix** → the `ID → module (behavior) → test` edges you must be able to
  point at for every ID by the end.

Record this list with `todo` — one entry per §9 test group (or per R/C cluster), each `blockedBy`
nothing, as your implementation order. This checklist *is* your proof that "everything got
implemented": every box closes on a green test that cites its spec ID.

### 0.3 Seed the lab skeleton (if empty)

Create the layout from the table above: `src/<pkg>/` with the modules named in the §4 contract
headers, `tests/`, `schemas/`, and a `pyproject.toml` (name/CLI entry point per §5.1, deps per
§10, `[tool.ruff]`/`[tool.pytest]` config as in peer labs). **Commit each skeleton step** —
`feats(<lab>): scaffold <pkg> + pyproject + test stubs` — so intermediate work lands on the
history before behavior is added.

---

# Phase 1 — Build with TDD (one §9 test group at a time)

Drive every bit of production code from `superpowers:test-driven-development`. Its Iron Law
governs:

```text
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST
```

For each T-nn group, run the red-green-refactor loop:

1. **RED — write the failing test first.** Translate the §9 T-nn line (+ the §8 E-nn edge it
   depends on, + the §6 I-nn it guards) into a concrete test. Name it after the behavior and
   the spec ID it proves, e.g. `test_zero_denominator_fallback` `# I-001, E-03`. Assert on
   **observable** behavior from §2/§4, not on internals. Cite the ID(s) in a comment so
   §11 traceability stays mechanically checkable (`grep` the tests for the ID, not for a free-text
   guess).
2. **Verify RED — watch it fail.** Run that one test; confirm it **fails** (not errors) for the
   right reason — the missing behavior, not a typo or an import. Errors? fix the test until it
   *fails correctly*, then proceed. A test that passes immediately is testing nothing — it
   already encodes existing code; delete it and test what you are about to build.
3. **GREEN — minimal code.** Write the *smallest* implementation that passes and keeps the
   others green. Do not add features, options, or polish the test does not require. Honor the
   §4 contract shape and the §6 invariant exactly.
4. **Verify GREEN — watch it pass.** Re-run the whole suite; confirm the new test passes and
   nothing else regressed and output is pristine (no warnings/errors). **Fix code, never the
   test, to reach green.**
5. **REFACTOR — clean up while green.** Remove duplication, name things, extract helpers.
   Keep every test green; add no behavior.
6. **Commit.** `feats(<lab>): <what the T-nn group realized>` — one commit per group or per
   cohesive slice. **Commit intermediate work; do not batch.**

Repeat until the §9 suite (and every I/K/E in §6/§7/§8) is green.

### The "implement everything" rule, concretely

- **Every** R/C/I/K/E/T in the spec is built. Close each with its green test.
- **Optional items** (`O-n`, `MAY`, `SHOULD`) are implemented *to the depth the spec states* —
  behind the flag/gate the §4/§5 contract describes (e.g. a `--mock`/opt-in real path, an
  optional GUI per §5.2), not omitted. If the spec says a GUI is "optional", you *build* it as
  the optional surface; "optional" ≠ "skip".
- **Never silently drop a spec item.** Omitting an in-scope requirement is a conformance failure
  you will catch in Phase 3. If the user told you to scope something out, record the exact spec
  ID(s) excluded and the reason in the README and the conformance report.
- **Diagnostics / verbosity (§5.3).** If the spec pins the universal verbosity contract,
  implement it: quiet by default; CLI `--verbose`/`--verbose INFO`/`--verbose DEBUG`; INFO =
  metadata only (no raw prompts/responses/secrets/payloads); DEBUG adds raw content to **stderr**
  leaving **stdout** unchanged; GUI `Off`/`INFO`/`DEBUG` defaulting to `Off` in a dedicated
  diagnostics view. Add its T-nn tests: bare `--verbose`, explicit `INFO`/`DEBUG`, invalid value
  exits `2`, stdout preserved under INFO/DEBUG.
- **Determinism.** Where §6 requires determinism / byte-stability, make the mock/offline path
  deterministic and add its invariant test (repeat with identical inputs → identical metrics /
  artifact).
- **Zero-denominator / edge semantics.** Implement the §8 E-nn outcomes (e.g. `n/m` for
  `cost_per_success` with zero successes, `1.0`/`0.0` documented fallbacks per I-001) — don't let
  them `ZeroDivisionError`.

### When a bug shows up mid-build

Route through `superpowers:systematic-debugging`: reproduce, write a **failing regression test**
(citing the E-nn/I-nn it fixes), then the same red-green loop. Never fix a bug without the test
that proves it — the fix and its guard land together. Do not edit a *passing* test to make a
*real* failure go away; fix the code or, if the test itself was wrong, explain which and why.

### Phase 1 exit gate (run before Phase 2)

Do not proceed until, all true:

```bash
uv run python -m pytest tests -q        # green, no skips on §9 T-nn, no warnings
uv run ruff check src tests             # clean
uv run <cli> --self-check               # if the spec pins the §5.1 boundary
```

Every §9 test group has a green test citing its ID; `grep -rnE 'I-0[0-9]{2}|E-0[0-9]|K-0[0-9]|T-0[0-9]'
tests` shows the invariants/edges/tests are anchored. Use
`superpowers:verification-before-completion` — evidence (the run output), not assertion.

---

# Phase 2 — Make README.md reflect reality

When the suite is green, **rewrite/refresh `README.md` from what was actually built**, not from
the plan. A drift where README describes an intended CLI the code does not have is a defect this
phase exists to prevent.

Model it on a peer lab's README (e.g. `labs/week1/chapter4/README.md`):

1. **Title + one-line what-it-does** — the §1 actors / §0 intent, in one sentence.
2. **Setup** — exact env (`Python 3.12` + `uv`), `uv sync --extra dev`, and any optional
   group (`--extra gui`, opt-in real/dependency path). State which paths are offline/deterministic.
3. **Quick start** — a copy-pasteable happy path using the **fixtures / sample data that exists**
   in the lab (`tests/fixtures/*`, `documents/`, `corpus/`). No invented data.
4. **Commands** — one subsection per CLI subcommand / public entry point actually in §5.1, with
   the real flags and the real **exit codes** (usage `2`, dataset/contract violations `3`,
   success `0`, etc. — whatever §5.1/§7 fixed). Mark optional surfaces (`--mock`, the GUI) exactly
   as the code gates them.
5. **Artifacts and schemas** — the versioned artifacts and `schemas/` the implementation writes,
   mirroring the §4 contract versions.
6. **Project layout** — an ASCII `+ - |` tree of the real `src/`, `tests/`, `schemas/` (each
   module's one-line role), generated from what exists, not from the spec's plan.
7. **Verification** — the exact commands from the Phase 1 exit gate, so the reader reproduces green.
8. **Scope/deferrals** — if the user scoped anything out, list the excluded spec ID(s) and why;
   otherwise state that the full spec was implemented.

After editing, re-render its PDF if the lab ships one: `cd` the lab and run `md2pdf.sh` per the
`md2pdf-authoring` skill, and commit `README.md` **and** the regenerated `README.pdf` together
(they must not drift). Commit as `docs(<lab>): README reflects built implementation`.

---

# Phase 3 — Proof: re-read the spec and audit every artifact

Implementation "works" is necessary; **conforms to the spec** is the goal. Do this pass
last, with fresh eyes, and write a short `SPEC_BUILD_REPORT.md` (or append to a peer's
`SPEC_REVIEW_REPORT.md` if that's where the lab tracks findings) so the work is auditable.

### 3.1 Re-read SPEC.md as a grader

Re-read the spec *whole again* — as if grading someone else's build. For **each spec family**,
walk the checklist from Phase 0 and, for every open ID, point at the concrete evidence:

| Walk | Check, per ID | Evidence to produce |
| --- | --- | --- |
| §2 R-nn | requirement observable in the build | the module + test that realizes it |
| §4 C-nn | contract shape honored (dataclass/JSON/module boundary) | the type / schema / file that pins it |
| §6 I-nn | invariant holds in the implementation | the invariant test (assert it, don't trust it) |
| §7 K-nn | measurable constraint met | exit-code / threshold check, or a test |
| §8 E-nn | edge semantics implemented | the edge test's actual outcome |
| §9 T-nn | acceptance test present and green | the test file + green run |
| §11 | every ID traces to module → behavior → test | fill the matrix from evidence; flag any broken edge |

Open the §11 traceability matrix and confirm **no ID is dangling** — every
`ID → module → test` edge points at real, green code. A dangling edge (an ID with no code, or
code with no test) is a conformance defect; open it as `F-0xx` and either fix it or confirm it
was an explicit user-directed deferral.

### 3.2 Cross-check the artifacts against the spec

Review *every* produced artifact — not just `src/` — for adherence:

- **Every contract (§4) file exists** with the pinned shape; names/fields/versions match the
  spec, not a close variant.
- **CLI surface (§5.1)** matches the spec's subcommand table (subcommands, flags, exit codes) —
  no extra/missing, no renamed flags.
- **`schemas/`** match the contract JSON-shapes; version numbers match §4.
- **Dependencies (§10)** are the ones the spec names; nothing the spec forbade sneaked in
  (e.g. a network/Ollama import the §6 boundary invariant says is forbidden — verify with the
  `--self-check` if pinned).
- **Data artifacts** written by the build are schema-valid and the shape the §4/§10 pins.
- **Determinism:** where required, re-run the offline path with identical inputs → identical
  result; the invariant test holds.
- **README (§ Phase 2)** describes what the code *does*, verified command-by-command (run the
  README's commands; every one works as written).
- **No silent omissions:** diff the Phase 0 checklist against reality — every in-scope box is
  closed, or its deferral is explicitly recorded with user approval.

### 3.3 Fix, then re-verify

For every defect found (`F-0xx`: location, what's off, why it matters, resolution): fix the
**code or the spec**, not the report. Prefer fixing the implementation to match the spec; only
edit `SPEC.md` (`fix(<lab>): ...`, bump its version header) when the spec itself was ambiguous or
wrong — and say so. After fixes, re-run the Phase 1 exit gate (green + clean lint +
self-check) and re-walk §3.1 until the walk is clean. Use
`superpowers:verification-before-completion`: paste the real (truncated) run output as evidence.

### Done when — all three hold

1. **Built:** §9 suite green (no skips on T-nn), lint clean, self-check (if pinned) passes; every
   R/C/I/K/E/T realized or explicitly deferral-recorded.
2. **Documented:** `README.md` (and its `README.pdf`) describe the running system, command-verified.
3. **Conforming:** the §11 matrix is fully traced; the §3.2 artifact cross-check found no open
   (unapproved) defect; `SPEC_BUILD_REPORT.md` records the per-ID evidence and the final verdict.

Report the verdict in one line, then stop:

```text
Spec coverage: <NN>/<NN> IDs realized (<k> deferred: <ids + why>)
Readiness: BUILT / BUILT WITH DEFERRALS / INCOMPLETE
Conformance: PASS / PASS WITH NOTES / FAIL
```

---

# Anti-rationalization checklist (stop and correct before "done")

- [ ] Wrote the failing **test first** for each T-nn and *watched it fail for the right reason*
      (no production code ahead of its test; `superpowers:test-driven-development` Iron Law held)
- [ ] Implemented **every** in-scope spec item; nothing silently dropped
- [ ] Optional items implemented to spec depth (**gated**, not omitted)
- [ ] §8 edge cases + §6 invariants (zero-denominator, determinism) have tests that assert the
      outcome, not just run the code
- [ ] §5.1 CLI subcommands/flags/exit codes match the spec exactly
- [ ] §5.3 verbosity contract built + tested (quiet default; INFO metadata-only on stdout; DEBUG
      raw to stderr; GUI Off default)
- [ ] Full suite green, no skips on T-nn, no warnings; lint clean; `--self-check` (if pinned) passes
- [ ] `README.md` rewritten from the built system; its commands all run as written; `README.pdf`
      regenerated together with the `.md`
- [ ] Every T-nn cites its spec ID so §11 traceability stays `grep`-able
- [ ] Re-read `SPEC.md`; §11 matrix fully traced (no dangling `ID → module → test` edge)
- [ ] Cross-checked **all** artifacts (src, tests, schemas, pyproject, data, README) against the
      spec; defects recorded and fixed; `SPEC_BUILD_REPORT.md` written
- [ ] Deferrals (if any) are explicit, user-approved, id-listed in both README and the report
- [ ] Verification is evidenced with real run output (`superpowers:verification-before-completion`)

> **The build succeeds when the implementation agent can point every spec ID at a green test, the
> README reads like the thing that was built, and a grader re-reading the spec and walking §11 finds
> nothing dangling — no undocumented intent left on either side of the contract.**
