# Hybrid Mortgage Calculator

Chapter 31 implements a fixed-rate, monthly-payment mortgage calculator with a deterministic financial core and an optional natural-language boundary.

## Setup

```bash
uv sync --extra test
uv run pytest
```

The test suite is offline and does not require an API key, model server, or network access.

## Direct calculation

Provide exactly three primary quantities. Annual rates are percentages by default; terms in years are converted to monthly payments.

```bash
uv run mortgage calculate \
  --principal 500000 \
  --rate 6.5 \
  --term-years 30
```

Use `--format json` for a machine-readable response. Decimal values are serialized as strings and integer counts as JSON integers.

## Natural-language mode

The default adapter is the deterministic offline mock:

```bash
uv run mortgage ask --adapter mock \
  'What is the payment on $500,000 at 6.5% for 30 years?'
```

The adapter interprets language and calls the same calculator tool used by direct mode. It never performs arithmetic itself. A real local Ollama adapter is available as an opt-in path:

```bash
ollama pull llama3.2
uv run mortgage ask --adapter real --model llama3.2 \
  'What is the payment on $500,000 at 6.5% for 30 years?'
```

`OLLAMA_HOST` defaults to `http://localhost:11434` and can be overridden with `--host`; `OLLAMA_MODEL` supplies the default model when `--model` is omitted. Ollama is used only for interpretation and explanation. The deterministic calculator tool remains authoritative for every financial number. Real-model failures return exit code `5` and never fall back to model-generated arithmetic.

## Amortization

Request a bounded schedule with:

```bash
uv run mortgage amortize \
  --principal 500000 \
  --rate 6.5 \
  --term-years 30 \
  --format json
```

Schedules are limited to 1,200 payment periods. The final payoff row is adjusted when needed to close the balance while preserving the payment identity.

## Scope and disclaimer

The calculator supports fixed-rate loans with monthly payments and principal-and-interest calculations only. It does not estimate taxes, insurance, HOA fees, lender fees, adjustable-rate loans, or lender-specific quotes.

Every response includes:

> Estimate for principal and interest only; not a lender-specific quote or financial advice.
