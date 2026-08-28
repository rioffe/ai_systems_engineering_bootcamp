# Monte Carlo Pi (PyQt5 + matplotlib)

A small desktop GUI that estimates π with the Monte Carlo method and visualizes
the convergence live.

## The idea

A quarter circle of radius 1 sits inside the unit square `[0, 1] × [0, 1]`.
Their areas are `π/4` and `1`, so the fraction of uniformly random points that
fall inside the circle (`x² + y² ≤ 1`) is `π/4`. Estimating that fraction
gives:

    π ≈ 4 · (points inside) / (total points)

The estimate converges to the true value of π as the sample count grows.

## Setup (with uv)

Everything is managed by `uv`. Python 3.12 and all dependencies (PyQt5,
matplotlib, numpy) are installed into an isolated virtualenv:

```bash
uv sync
```

## Run

From the project directory:

```bash
# via the installed console script entry point
uv run monte-carlo-pi

# or as a module
uv run python -m monte_carlo_pi
```

## Controls

- **Add 1M points** — sample one million random points (added in batches on a
  background thread so the UI stays responsive).
- **Add 10M (to total)** — sample up to ten million points total.
- **Stop** — halt the current sampling run.
- **Reset** — clear the plot and statistics.

The left panel shows the live scatter of sampled points inside/outside the
quarter circle; the right panel shows the running π estimate versus sample count
against the true value of π (dashed line). The status bar reports the current
sample/inside counts and the estimate with its error.

## Layout

- `src/monte_carlo_pi/app.py` – the GUI, plotting, and `PiEstimatorThread`.
- `src/monte_carlo_pi/__init__.py` – package entry (`main`).
- `src/monte_carlo_pi/__main__.py` – enables `python -m monte_carlo_pi`.
- `pyproject.toml` – project metadata and dependencies.
