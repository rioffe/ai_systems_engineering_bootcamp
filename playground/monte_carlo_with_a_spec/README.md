# monte-carlo-pi

A PyQt5 + matplotlib GUI that estimates the mathematical constant **π** using the
Monte Carlo method (random points in a unit square, counting the fraction inside
the quarter circle), with a live scatter plot and a π̂-convergence plot.

> The authoritative description of behavior, contracts, invariants, edge cases, and
> acceptance criteria for this project is **`SPEC.md`**. Implementation should be
> derived from it; see `SPEC.md § Traceability` for the id mapping.

## Requirements

- Python **3.12** (managed by `uv`)
- Display: a desktop session (GUI). Headless CI uses the Qt `offscreen` platform.

## Development setup

```bash
uv sync            # creates .venv (Python 3.12) and installs deps
uv run pytest      # run the test / eval suite (offscreen Qt)
uv run monte-carlo-pi   # launch the GUI
```
