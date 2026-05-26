# Current System State

- Run timestamp: `2026-05-26T14:21:28.982384+05:30`
- Run ID: `research-portfolio-multi`
- Universe: `HAL, IRCTC, BSE`
- Requested start date: `2016-01-01`
- Effective start date: `2019-10-14`
- Analysis end date: `2026-05-25`
- Analyzed trading days: `1642`
- Analyzed years approx: `6.52`
- Winning candidate: `franchise_pullback_accumulator`
- Winning candidate status: `REJECTED_NEGATIVE_EDGE`
- Best gross-edge candidate: `franchise_breakout_confirmed`
- Best net-edge candidate: `franchise_seasonality_enabled`
- Best hold-quality candidate: `franchise_breakout_confirmed`
- Lowest drawdown-duration candidate: `franchise_breakout_confirmed`
- Most promising candidate: `franchise_seasonality_enabled`
- Most promising candidate behavior: `short_horizon_churn`
- Active selector model: `adaptive_switch`
- Current selected HAL strategy: `franchise_pullback_accumulator`
- Current exit policy behavior: `HOLD_CORE`
- Selected strategy mix: `franchise_breakout_confirmed:0.01, franchise_event_drift:0.00, franchise_pullback_accumulator:0.99, franchise_risk_managed:0.00`
- HAL tradable under any candidate: `False`
- HAL research status: `RESEARCH_BLOCKED`
- Portfolio readiness status: `PORTFOLIO_BLOCKED`
- Deployable benchmark status: `RESEARCH_ONLY`
- Default deployable subset: `HAL, IRCTC, BSE`
- Closest viability blocker: `drawdown_duration_days`
- HAL single-symbol binding blocker: `avg_holding_period_days`
- Portfolio-ready binding blocker: `drawdown_duration_days`
- Walk-forward confidence: `low`
- Behavior style: `owner_style_holding`
- Best aligned symbols: ``
- Top rejection reasons: `REJECTED_DRAWDOWN_DURATION, REJECTED_HOLDING_PERIOD, REJECTED_CONCENTRATION`

## Metrics
- CAGR: `-0.011283`
- Sharpe: `-0.322219`
- Sortino: `-0.099737`
- Max drawdown: `0.095157`
- Drawdown duration days: `1039.0`
- Turnover: `20.000000`
- Win rate: `0.200000`
- Payoff ratio: `0.893045`
- Profit factor: `0.223261`
- Avg holding period days: `24.050000`
- Portfolio heat max: `0.209055`
- Avg concurrent positions: `0.177223`
- Max concurrent positions used: `2`
- Days with any position %: `0.152862`
- Days with 2+ positions %: `0.024361`
- Days with 3 positions %: `0.000000`
- Cash idle %: `0.847138`
- Average invested capital %: `0.014732`

## Metric Drivers
- Gross CAGR proxy: `-0.071270`
- Gross Sharpe proxy: `-0.253832`
- Gross Sortino proxy: `-0.031349`
- Gross profit factor: `0.251531`
- Gross payoff ratio: `1.006123`
- Median holding period days: `20.0`
- P75 holding period days: `33.0`
- Trades under 5d %: `0.150000`
- Profit from 15d+ holds %: `1.000000`
- Entry threshold floor: `0.580000`
- Hold threshold floor: `0.470000`
- Time stop bars: `30`
- ATR stop multiplier: `2.000000`
- Slippage bps: `5.000000`
- STT buy/sell bps: `10.000000` / `10.000000`

## Most Promising Candidate
- Candidate: `franchise_seasonality_enabled`
- Status: `REJECTED_DRAWDOWN_DURATION`
- CAGR: `0.000236`
- Sharpe: `0.044780`
- Profit factor: `0.763790`
- Avg holding days: `3.722222`
- Drawdown duration days: `583.0`
- Trades under 5d %: `0.555556`
- Profit from 15d+ holds %: `0.000000`

## Candidate Notes
- Candidate modules enabled: `trend, pullback, momentum_quality, fundamental_quality, liquidity_gate, regime_gate, staged_entries, partial_exits, seasonality`
- Candidate modules disabled: `event_drift`
- Event drift: `on` because `bounded event window`
- Seasonality: `off` because `not validated`
- Current HAL recommendation: `exclude`
- Symbol recommendations: `HAL:exclude, IRCTC:accumulate-only, BSE:exclude`
- `HAL`: `exclude`
- `IRCTC`: `accumulate-only`
- `BSE`: `exclude`

## Benchmark
- Benchmark winner scope: `HAL`
- Strict portfolio-ready scope: `n/a`
- Excluded symbols: ``
- Ghost symbols: ``
- Data problem symbols: ``
- Slot block reasons: `invalid_entry_state:11`
- Entry blocker leaderboard: `REGIME_UNSUITABLE:7104, EVENT_BLACKOUT:174, REENTRY_COOLDOWN_ACTIVE:101`
- Allocator blocker leaderboard: `invalid_entry_state:11`
- Screening pass rates: `BSE:0.27, HAL:0.27, IRCTC:0.27`
- Actionable signal rates: `BSE:0.02, HAL:0.03, IRCTC:0.02`
- Trade conversion rates: `BSE:0.21, HAL:0.16, IRCTC:0.18`
- Hard-risk exit rates: `BSE:0.57, HAL:1.00, IRCTC:0.83`
- Active per-symbol overrides: `HAL:strict_quality; IRCTC:relaxed_screening; BSE:strict_breakout`
- Deployment bottleneck: `screening`

## Baseline Comparison
- Cash idle delta: `-0.018270`
- Days with any position delta: `0.018270`
- Days with 2+ positions delta: `0.000000`
- Avg holding period delta: `1.669048`
- Gross edge delta: `-0.003866`
- Net edge delta: `-0.000631`
- Hard-risk exit rate delta: `0.000000`
- Selector mix delta: `n/a`

## Period Highlights
- Latest week: `2026-W22` | return `0.000000` | trades `0.0` | mix `franchise_pullback_accumulator:1.00`
- Latest month: `2026-05` | return `0.000000` | trades `0.0` | mix `franchise_pullback_accumulator:1.00`
- Latest quarter: `2026-Q2` | return `0.000000` | trades `0.0` | mix `franchise_pullback_accumulator:1.00`
- Latest year: `2026` | return `0.000000` | trades `0.0` | mix `franchise_pullback_accumulator:1.00`
- Overall: `full_sample` | return `-0.071270` | trades `20.0` | mix `franchise_breakout_confirmed:0.01, franchise_event_drift:0.00, franchise_pullback_accumulator:0.99, franchise_risk_managed:0.00`

## Interpretation
- System does not currently have positive edge.
- Main failure mode is drawdown-duration persistence.
- Candidate rejection is functioning and the current winner is not investable.
- Current best candidate is behaving more like ownership than churn.
- HAL is not currently tradable; closest candidate is franchise_seasonality_enabled.
