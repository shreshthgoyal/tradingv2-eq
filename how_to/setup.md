# Setup

## Runtime

- Python `3.12+` is required.
- Node.js is required for the preferred `screener-scraper-pro` path.
- If the Node path is unavailable, the runner falls back to the built-in Python Screener HTML parser.

## Python environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
```

## Node dependencies

```bash
npm install
```

## Config

The default config is [config/system.yaml](/Users/shreshth1/Documents/trading/config/system.yaml).

The validated phase-1 settings are:
- symbol universe starts with `HAL`
- benchmark is `NIFTY 50`
- research outputs land under `artifacts/`
- walk-forward defaults are `3` training years and `1` test year

## Notes

- MongoDB is not required for the supported phase-1 run path.
- Dashboard, paper trading, and live execution are out of scope for the validated command surface in this phase.
