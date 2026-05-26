# Troubleshooting

## `python3.12` is missing

The supported runner requires Python `3.12+`. Install Python `3.12`, recreate the virtual environment, and reinstall the package.

## `node` or `npm install` is missing

The preferred Screener path uses `screener-scraper-pro` through the Node helper. If Node is unavailable, the runner falls back to the Python HTML parser, but you should still expect better structural fidelity from the package path.

## `nselib` returns unexpected numeric strings

Some NSE fields may contain placeholders like `-`. The adapter normalizes these to `0.0`, but if NSE changes response formats further, inspect:

- [src/tradingbot/data_ingest/nselib_adapter/adapter.py](/Users/shreshth1/Documents/trading/src/tradingbot/data_ingest/nselib_adapter/adapter.py)

## Historical coverage is shorter than 10 years

The current validated HAL dataset started at `2018-03-28` and ended at `2026-05-22`. The system prefers 10 years where available but does not assume that the source will always provide it.

## Screener package path fails

If the Node fetch fails, the adapter falls back to the Python HTML parser. Inspect:

- [src/tradingbot/data_ingest/screener_adapter/adapter.py](/Users/shreshth1/Documents/trading/src/tradingbot/data_ingest/screener_adapter/adapter.py)
- [src/tradingbot/data_ingest/screener_adapter/fallback_parser.py](/Users/shreshth1/Documents/trading/src/tradingbot/data_ingest/screener_adapter/fallback_parser.py)

## Where to inspect the runnable entrypoint

The phase-1 historical runner entrypoint is:

- [research_run.py](/Users/shreshth1/Documents/trading/src/tradingbot/jobs/research_run.py)
