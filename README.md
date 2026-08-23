# AI Systems Engineering Bootcamp

This repository contains the curriculum outline and tools for the **AI Systems Engineering Bootcamp**. The curriculum focuses on the transition from traditional software engineering to AI systems engineering, emphasizing reliability, observability, and agentic workflows.

## Contents

- `outline.md`: The core curriculum structure, broken down by weeks and days.
- `md2pdf.sh`: A utility script to convert the Markdown curriculum into a professional PDF format using `pandoc` and `xelatex`.
- `outline.pdf`: The generated PDF version of the curriculum.
- [book-local.pdf](https://github.com/rioffe/ai_systems_engineering_bootcamp/blob/main/book-local.pdf): The full bootcamp book (branded copy).

## Curriculum Overview

The bootcamp covers four key pillars of AI engineering:
1. **Building & Deploying AI Applications**: Creating reliable systems around probabilistic models.
2. **Software Engineering Fundamentals**: Architecting systems with the right tradeoffs.
3. **Using Coding Agents**: Learning to supervise and orchestrate AI agents.
4. **Shaping the Build**: Product design, evaluation, and deployment.

## Using the `md2pdf.sh` Tool

The `md2pdf.sh` script uses `pandoc` and `xelatex` to generate a PDF from the Markdown file.

### Prerequisites

Ensure you have the following installed:
- `pandoc`
- `XeLaTeX` (e.g., via TeX Live)

### Usage

Give the script execution permissions:
```bash
chmod +x md2pdf.sh
```

Generate the PDF from the markdown outline:
```bash
./md2pdf.sh outline.md
```

To generate a PDF with a **Table of Contents**:
```bash
./md2pdf.sh --toc outline.md
```

## License

[Specify License, e.g., MIT]
