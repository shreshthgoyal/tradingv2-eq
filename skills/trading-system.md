# Trading System Skill

This repository builds and maintains a local NSE cash-equity EOD trading system.

## Invariants

- Cash equity only
- Long only
- EOD decisions only
- Next-session execution only
- Python 3.12+ runtime
- `nselib` is the primary NSE market-data package
- `screener-scraper-pro` is the primary fundamentals package
- `nsetools` is optional fallback only
- Phase-1 validated path is non-persistent and research-only
- Every research run must emit JSON and Markdown artifacts with signal and trade reasoning
