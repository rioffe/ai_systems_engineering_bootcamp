# AI Systems Engineering Bootcamp

This repository contains the curriculum and build tooling for the **AI Systems Engineering Bootcamp**. The course focuses on the transition from traditional software engineering to AI systems engineering, emphasizing reliability, observability, and agentic workflows.

## Curriculum Overview

The bootcamp covers four key pillars of AI engineering (mapped to Ng's four skills):

1. **Building & Deploying AI Applications** (Week 1): Creating reliable systems around probabilistic models.
2. **Software Engineering Fundamentals** (Week 2): Architecting systems with the right tradeoffs.
3. **Using Coding Agents** (Week 3): Learning to supervise and orchestrate AI agents.
4. **Shaping the Build** (Week 4): Product design, evaluation, and deployment.

## Table of Contents

Reading order: front matter, then the 30 chapters grouped by week (Weeks 1–4 map to
the four pillars above). Links point to the source Markdown, which renders on
GitHub; for ready-to-read PDFs, see the [assembled book](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/book.pdf)
and the [two-level-TOC book](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/book-local.pdf) in the [Repository layout](#repository-layout) below.

### Front matter

- [Introduction](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/introduction.md)
- [License](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/license.md)

### Week 1 — Building & Deploying AI Applications

- [Chapter 1: Building AI Applications](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/week1/chapter1.md)
- [Chapter 2: Context Engineering](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/week1/chapter2.md)
- [Chapter 3: Retrieval-Augmented Generation](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/week1/chapter3.md)
- [Chapter 4: Evals](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/week1/chapter4.md)
- [Chapter 5: Agentic Workflows](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/week1/chapter5.md)
- [Chapter 6: Production AI](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/week1/chapter6.md)
- [Chapter 7: Week 1 Project](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/week1/chapter7.md)

### Week 2 — Software Engineering Fundamentals

- [Chapter 8: Architecture: Designing AI Systems That Scale](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/week2/chapter8.md)
- [Chapter 9: Data Systems: Designing the State and Information Layer](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/week2/chapter9.md)
- [Chapter 10: Reliability Engineering](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/week2/chapter10.md)
- [Chapter 11: Security](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/week2/chapter11.md)
- [Chapter 12: Performance and Economics](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/week2/chapter12.md)
- [Chapter 13: Testing AI Systems](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/week2/chapter13.md)
- [Chapter 14: Architecture Review](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/week2/chapter14.md)

### Week 3 — Using Coding Agents

- [Chapter 15: How Coding Agents Work](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/week3/chapter15.md)
- [Chapter 16: Specification Engineering](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/week3/chapter16.md)
- [Chapter 17: Agent Context Management](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/week3/chapter17.md)
- [Chapter 18: Agentic Development Loops](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/week3/chapter18.md)
- [Chapter 19: Multi-Agent Systems](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/week3/chapter19.md)
- [Chapter 20: Coding-Agent Safety](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/week3/chapter20.md)
- [Chapter 21: The Agentic Software Project](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/week3/chapter21.md)

### Week 4 — Shaping the Build

- [Chapter 22: Product Thinking](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/week4/chapter22.md)
- [Chapter 23: AI-Native Product Design](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/week4/chapter23.md)
- [Chapter 24: MVP Design](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/week4/chapter24.md)
- [Chapter 25: Build](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/week4/chapter25.md)
- [Chapter 26: User Testing](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/week4/chapter26.md)
- [Chapter 27: Production Hardening](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/week4/chapter27.md)
- [Chapter 28: Final Evaluation](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/week4/chapter28.md)
- [Chapter 29: Architecture and Product Review](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/week4/chapter29.md)
- [Chapter 30: The AI Engineer's Future](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/curriculum/week4/chapter30.md)

## Repository layout

- `outline.md`: The top-level, master curriculum structure — 4 weeks / 30 days laid out at a glance.
- `curriculum/`: The chapter-by-chapter authoring tree:
  - `introduction.md` / `introduction.pdf`: The Introduction front matter prepended to the book.
  - `week1/` … `week4/`: One folder per week. Each holds:
    - `day<N>.md` — daily notes / outlines for that day.
    - `chapter<N>.md` (+ its generated `chapter<N>.pdf`) — the canonical numbered chapters (30 total, `chapter1`–`chapter30`).
    - `*_v2.md` — in-progress draft revisions of a few week-1 chapters.
- [book.pdf](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/book.pdf): The full assembled book — the Introduction + all 30 chapters in one PDF, with a master table of contents and title page.
- [book-local.pdf](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/book-local.pdf): The same book with a **two-level table of contents** — a front-matter chapter list plus a compact per-chapter "Contents" page. This is the local working copy (currently carries a name on the title page).
- `outline.pdf`: A single-PDF render of `outline.md`, kept for reference.
- Build tooling:
  - `Makefile`: The build driver — the normal way to generate PDFs (see below).
  - `tools/build-book.sh`: Assembles `book.pdf` (concats every canonical chapter and runs pandoc once).
  - `tools/build-book-localtoc.sh`: Assembles `book-local.pdf` with the two-level TOC.
  - `tools/regen-ch-targets.py`: Regenerates the per-chapter `ch<N>` targets inside the `Makefile`.
  - `md2pdf.sh`: The underlying Markdown→PDF converter (pandoc + XeLaTeX); drives every target above.
  - `.pi/skills/md2pdf-authoring/SKILL.md`: Authoring / conversion playbook (preprocessor, pitfalls, exit-code masking).

## Building PDFs

Generating PDFs is driven by the **Makefile**, which wraps `md2pdf.sh` (the converter itself is invoked via `bash`, so it does not need to be executable when called through `make`).

### Prerequisites

- `pandoc`
- `XeLaTeX` (e.g., via TeX Live)
- `Python 3` — for `make gen-ch` (regenerating chapter targets)
- `shellcheck` — for `make lint`
- `Chromium` / `Chrome` — **only** for chapters that embed mermaid diagrams (currently just `week1/chapter1.md`). The binary is auto-detected and overridable via `PUPPETEER_EXECUTABLE_PATH`.

### Make targets

| Command | What it does |
| ------- | ------------ |
| `make` | Build every canonical chapter `*.pdf` (`--toc`; `+--mermaid` where used). |
| `make ch<N>` | Build a single chapter by number, e.g. `make ch7`. |
| `make one T=week1/chapter1.md` | Build one chapter by path with auto-detected flags. |
| `make book` | Assemble the full book → `book.pdf` (master TOC, title page). |
| `make book-local` | Assemble the book with a two-level TOC → `book-local.pdf`. |
| `make clean` | Remove generated chapter `*.pdf` under `curriculum/week*/`. |
| `make lint` | `shellcheck md2pdf.sh`. |
| `make gen-ch` | Regenerate the `ch<N>` target block after adding/removing a chapter (then commit the `Makefile`). |

Overridable variables: `CHAPTERS`, `MERMAID_CHAPTERS`, `TITLE`, `AUTHOR`, and `INTRO=0` (omit the Introduction front matter). A single broken chapter is reported but does not abort the run.

### Using `md2pdf.sh` directly

The Makefile is a thin wrapper. To convert a single chapter yourself, `md2pdf.sh` resolves paths relative to its **current working directory**, so `cd` into the chapter's folder first:

```bash
chmod +x md2pdf.sh
cd curriculum/week1

./md2pdf.sh chapter3.md                 # plain
./md2pdf.sh --toc chapter3.md           # with a table of contents
./md2pdf.sh --toc --mermaid chapter1.md # + mermaid diagrams (needs Chrome)
```

To build the whole book in one go, prefer the Makefile targets above (`make book` / `make book-local`).

## License

This project — the curriculum, books, and accompanying tooling — is released under the **Creative Commons Attribution 4.0 International License** ([CC BY 4.0](LICENSE)):

- Deed: https://creativecommons.org/licenses/by/4.0/
- Legal code: https://creativecommons.org/licenses/by/4.0/legalcode

> **Copyright © 2026 Robert Ioffe — <https://github.com/rioffe>**

You are free to use, share, and adapt this material for any purpose, **including commercial**, provided you give **appropriate credit** to Robert Ioffe (<https://github.com/rioffe>), include a link to the license, and indicate if changes were made (and in no way that suggests the author endorses your use).
