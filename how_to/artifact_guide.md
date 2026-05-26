# Artifact Guide

Each research run writes a dedicated folder:

- `artifacts/<run_id>/summary.json`
- `artifacts/<run_id>/signals.json`
- `artifacts/<run_id>/trades.json`
- `artifacts/<run_id>/daily_states.json`
- `artifacts/<run_id>/dataset_report.json`
- `artifacts/<run_id>/summary.md`
- `artifacts/<run_id>/runbook.md`
- `artifacts/<run_id>/candidate_results.json`
- `artifacts/<run_id>/candidate_comparison.md`

## File meanings

`summary.json`
- aggregate metrics
- backtest execution assumptions
- run id and symbol

`signals.json`
- one row per trade date
- regime evidence
- screening pass/fail state
- module scores
- composite score
- reason codes

`trades.json`
- entry and exit lifecycle records
- next-session execution assumption
- reason codes for entries and exits

`daily_states.json`
- daily cash
- position quantity
- close price
- NAV
- regime label
- signal state

`dataset_report.json`
- first and last available dates
- missing ranges
- unavailable factor families
- assumptions applied
- degraded fields

`candidate_results.json`
- per-candidate metrics
- candidate acceptance/rejection status

`candidate_comparison.md`
- compact comparison table for candidate strategies
- quick view of CAGR, Sharpe, and max drawdown

## Current validated HAL run

Useful files from the validated HAL run:

- [summary.json](/Users/shreshth1/Documents/trading/artifacts/research-hal-2016-01-01/summary.json)
- [dataset_report.json](/Users/shreshth1/Documents/trading/artifacts/research-hal-2016-01-01/dataset_report.json)
- [summary.md](/Users/shreshth1/Documents/trading/artifacts/research-hal-2016-01-01/summary.md)

Useful files from the validated multi-stock run:

- [summary.json](/Users/shreshth1/Documents/trading/artifacts/research-portfolio-multi/summary.json)
- [candidate_results.json](/Users/shreshth1/Documents/trading/artifacts/research-portfolio-multi/candidate_results.json)
- [candidate_comparison.md](/Users/shreshth1/Documents/trading/artifacts/research-portfolio-multi/candidate_comparison.md)
