# Trading Strategy Research

Use this guidance before changing HAL strategy logic or interpreting backtest results.

## Diagnostic order

1. Parse:
   - fallback winner
   - most promising candidate
   - top rejection reasons
   - gross vs net metrics
   - hold-quality metrics
2. Fix the binding blocker first.
3. Do not treat low-trade-count profit factors as trustworthy.

## HAL-first rules

- HAL remains the default research universe.
- For HAL-only runs, separate:
  - `hal_single_symbol` research status
  - `portfolio_multi_symbol` readiness status
- Do not claim portfolio readiness from single-symbol results.

## Strategy selection

- Prefer breakout confirmation when:
  - long-trend quality is high
  - breakout confirmation is high
  - relative strength is strong
- Prefer pullback accumulation when:
  - long trend is intact
  - pullback quality is strong
  - breakout quality is weak
- Use risk-managed behavior when:
  - volatility rises while the position is already open
- Use event-drift only as a bounded HAL overlay, not a default mode.
- Keep seasonality disabled unless research explicitly validates it.

## Cost and hold logic

- NSE delivery cost floor is meaningful; short holds are punished.
- Improve edge in this order:
  1. positive gross edge
  2. acceptable hold quality
  3. positive net edge
  4. lower drawdown persistence
- Treat `profit_from_15d_plus_pct` as a core ownership metric.

## Exit logic

- Do not fully exit profitable positions on small score deterioration.
- Sell later tranches before the core tranche.
- Prefer:
  - `HOLD_WEAKNESS`
  - `REDUCE_ON_EXTENSION`
  - `REDUCE_ON_REGIME_SOFTENING`
  over immediate full exits unless risk is broken.

## Current interpretation discipline

- If fallback winner and most promising candidate differ, optimize the most promising one.
- If drawdown duration is the main blocker in HAL-only mode, report it as a research blocker and portfolio blocker separately.
- Always refresh `skills/current-system-state.md` after every run, including failed runs.
