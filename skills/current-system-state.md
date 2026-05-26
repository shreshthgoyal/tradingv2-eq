# Current System State

- Run timestamp: `2026-05-26T12:55:56.724946+05:30`
- Run ID: `research-portfolio-multi`
- Universe: `HAL, IRCTC, BSE`
- Requested start date: `2016-01-01`
- Effective start date: `2019-10-14`
- Analysis end date: `2026-05-25`
- Analyzed trading days: `1642`
- Analyzed years approx: `6.52`
- Winning candidate: `franchise_pullback_accumulator`
- Winning candidate status: `REJECTED_NEGATIVE_EDGE`
- Best gross-edge candidate: `franchise_pullback_accumulator`
- Best net-edge candidate: `franchise_pullback_accumulator`
- Best hold-quality candidate: `franchise_breakout_confirmed`
- Lowest drawdown-duration candidate: `franchise_breakout_confirmed`
- Most promising candidate: `franchise_pullback_accumulator`
- Most promising candidate behavior: `short_horizon_churn`
- Active selector model: `adaptive_switch`
- Current selected HAL strategy: `franchise_pullback_accumulator`
- Current exit policy behavior: `HOLD_CORE`
- Selected strategy mix: `franchise_breakout_confirmed:0.01, franchise_pullback_accumulator:0.99, franchise_risk_managed:0.00`
- HAL tradable under any candidate: `False`
- HAL research status: `RESEARCH_BLOCKED`
- Portfolio readiness status: `PORTFOLIO_BLOCKED`
- Deployable benchmark status: `RESEARCH_ONLY`
- Default deployable subset: `HAL, IRCTC, BSE`
- Closest viability blocker: `gross_edge`
- HAL single-symbol binding blocker: `gross_edge`
- Portfolio-ready binding blocker: `gross_edge`
- Walk-forward confidence: `low`
- Behavior style: `owner_style_holding`
- Best aligned symbols: ``
- Top rejection reasons: `REJECTED_NEGATIVE_EDGE, REJECTED_DRAWDOWN_DURATION, REJECTED_HOLDING_PERIOD`

## Metrics
- CAGR: `-0.010652`
- Sharpe: `-0.305331`
- Sortino: `-0.085577`
- Max drawdown: `0.093863`
- Drawdown duration days: `1039.0`
- Turnover: `21.000000`
- Win rate: `0.285714`
- Payoff ratio: `0.609313`
- Profit factor: `0.243725`
- Avg holding period days: `22.380952`
- Portfolio heat max: `0.225057`
- Avg concurrent positions: `0.158952`
- Max concurrent positions used: `2`
- Days with any position %: `0.134592`
- Days with 2+ positions %: `0.024361`
- Days with 3 positions %: `0.000000`
- Cash idle %: `0.865408`
- Average invested capital %: `0.013654`

## Metric Drivers
- Gross CAGR proxy: `-0.067404`
- Gross Sharpe proxy: `-0.240116`
- Gross Sortino proxy: `-0.020362`
- Gross profit factor: `0.277542`
- Gross payoff ratio: `0.693854`
- Median holding period days: `20.0`
- P75 holding period days: `28.0`
- Trades under 5d %: `0.095238`
- Profit from 15d+ holds %: `0.946160`
- Entry threshold floor: `0.580000`
- Hold threshold floor: `0.470000`
- Time stop bars: `30`
- ATR stop multiplier: `2.000000`
- Slippage bps: `5.000000`
- STT buy/sell bps: `10.000000` / `10.000000`

## Most Promising Candidate
- Candidate: `franchise_pullback_accumulator`
- Status: `REJECTED_NEGATIVE_EDGE`
- CAGR: `-0.001567`
- Sharpe: `0.020674`
- Profit factor: `0.482246`
- Avg holding days: `3.400000`
- Drawdown duration days: `680.0`
- Trades under 5d %: `0.700000`
- Profit from 15d+ holds %: `0.000000`

## Candidate Notes
- Candidate modules enabled: `trend, pullback, momentum_quality, fundamental_quality, liquidity_gate, regime_gate, staged_entries, partial_exits`
- Candidate modules disabled: `event_drift, seasonality`
- Event drift: `off` because `event overlay not selected by adaptive switch`
- Seasonality: `off` because `not validated`
- Current HAL recommendation: `exclude`
- Symbol recommendations: `HAL:exclude, IRCTC:exclude, BSE:down-rank`
- `HAL`: `exclude`
- `IRCTC`: `exclude`
- `BSE`: `down-rank`

## Benchmark
- Benchmark winner scope: `HAL`
- Strict portfolio-ready scope: `n/a`
- Excluded symbols: ``
- Ghost symbols: ``
- Data problem symbols: ``
- Slot block reasons: `invalid_entry_state:28`
- Entry blocker leaderboard: `REGIME_UNSUITABLE:7188, EVENT_BLACKOUT:174, REENTRY_COOLDOWN_ACTIVE:75`
- Allocator blocker leaderboard: `invalid_entry_state:28`
- Screening pass rates: `BSE:0.27, HAL:0.27, IRCTC:0.27`
- Actionable signal rates: `BSE:0.02, HAL:0.02, IRCTC:0.02`
- Trade conversion rates: `BSE:0.21, HAL:0.18, IRCTC:0.18`
- Hard-risk exit rates: `BSE:0.71, HAL:0.86, IRCTC:0.71`
- Active per-symbol overrides: `HAL:strict_quality; IRCTC:relaxed_screening; BSE:strict_breakout`

## Period Highlights
- Latest week: `2026-W22` | return `0.000000` | trades `0.0` | mix `franchise_pullback_accumulator:1.00`
- Latest month: `2026-05` | return `0.000000` | trades `0.0` | mix `franchise_pullback_accumulator:1.00`
- Latest quarter: `2026-Q2` | return `0.000000` | trades `0.0` | mix `franchise_pullback_accumulator:1.00`
- Latest year: `2026` | return `0.000000` | trades `0.0` | mix `franchise_pullback_accumulator:1.00`
- Overall: `full_sample` | return `-0.067403` | trades `21.0` | mix `franchise_breakout_confirmed:0.01, franchise_pullback_accumulator:0.99, franchise_risk_managed:0.00`

## Interpretation
- System does not currently have positive edge.
- Main failure mode is weak gross edge.
- Candidate rejection is functioning and the current winner is not investable.
- Current best candidate is behaving more like ownership than churn.
- HAL is not currently tradable; closest candidate is franchise_pullback_accumulator.
