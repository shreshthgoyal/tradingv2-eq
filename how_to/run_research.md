# Run Research

## Default command

From the repo root:

```bash
source .venv/bin/activate
python -m tradingbot.jobs.research_run --config config/system.yaml --benchmark "NIFTY 50"
```

This uses the full config-driven universe from [system.yaml](/Users/shreshth1/Documents/trading/config/system.yaml).

## Single-symbol run

```bash
python -m tradingbot.jobs.research_run --config config/system.yaml --symbol HAL --benchmark "NIFTY 50"
```

## Optional overrides

You can constrain the run window or change the output directory:

```bash
python -m tradingbot.jobs.research_run \
  --config config/system.yaml \
  --symbol HAL \
  --benchmark "NIFTY 50" \
  --start-date 2019-01-01 \
  --end-date 2026-05-25 \
  --artifacts-dir artifacts
```

## What the command does

The runner:

1. loads config
2. fetches historical HAL price and delivery data from `nselib`
3. fetches benchmark and VIX history from `nselib`
4. fetches historical fundamentals and shareholding from `screener-scraper-pro` or the Python fallback
5. builds typed in-memory `ResearchDataset` objects per symbol
6. computes daily indicators, regimes, screening states, and candidate master-strategy signals
7. runs cost-aware candidate research over the configured universe
8. ranks candidates and writes JSON and Markdown artifacts to the run folder

## Validated example

This repo was previously validated with a single-symbol HAL run:

```bash
/tmp/tradingbot_venv/bin/python -m tradingbot.jobs.research_run --config config/system.yaml --symbol HAL --benchmark "NIFTY 50"
```

That run completed successfully on `2026-05-25` and wrote artifacts under:

- [artifacts/research-hal-2016-01-01](/Users/shreshth1/Documents/trading/artifacts/research-hal-2016-01-01)
