from __future__ import annotations

from tradingbot.core.enums import RegimeLabel
from tradingbot.core.models import IndicatorSnapshot, ResearchDataset, ScreeningObservation


class HistoricalScreeningEngine:
    def evaluate(
        self,
        dataset: ResearchDataset,
        indicators: list[IndicatorSnapshot],
        regimes,
    ) -> list[ScreeningObservation]:
        regime_map = {item.trade_date: item for item in regimes}
        observations: list[ScreeningObservation] = []
        latest_fundamentals = dataset.screener_history.latest_snapshot
        event_dates = set(dataset.event_calendar.keys())
        for indicator in indicators:
            passed_checks: list[str] = []
            failed_checks: list[str] = []
            risk_flags: list[str] = []
            values = indicator.values
            regime = regime_map.get(indicator.trade_date)

            if values.get("turnover_ma_20", 0.0) >= 100000000:
                passed_checks.append("LIQUIDITY_OK")
            else:
                failed_checks.append("LIQUIDITY_LOW")
            if values.get("delivery_ma_20", 0.0) >= 25.0:
                passed_checks.append("DELIVERY_OK")
            else:
                failed_checks.append("DELIVERY_LOW")
            if 0.0 < values.get("realized_vol_20d", 0.0) <= 0.80:
                passed_checks.append("VOLATILITY_OK")
            else:
                failed_checks.append("VOLATILITY_EXTREME")
            if abs(values.get("distance_to_sma_20", 0.0)) <= 0.15:
                passed_checks.append("GAP_RISK_OK")
            else:
                failed_checks.append("GAP_RISK_HIGH")
            if indicator.trade_date not in event_dates:
                passed_checks.append("EVENT_WINDOW_OK")
            else:
                failed_checks.append("EVENT_BLACKOUT")
            if latest_fundamentals.promoter_pledge <= 20.0:
                passed_checks.append("PROMOTER_PLEDGE_OK")
            else:
                failed_checks.append("PROMOTER_PLEDGE_HIGH")
            if latest_fundamentals.debt_to_equity <= 1.5 and latest_fundamentals.roce >= 12.0:
                passed_checks.append("FUNDAMENTAL_FLOOR_OK")
            else:
                failed_checks.append("FUNDAMENTAL_FLOOR_WEAK")
            if values.get("relative_strength_63d", 0.0) >= -0.05:
                passed_checks.append("RELATIVE_STRENGTH_OK")
            else:
                failed_checks.append("RELATIVE_STRENGTH_WEAK")
            if regime and regime.label in {RegimeLabel.BULL_TRENDING, RegimeLabel.BULL_RANGING}:
                passed_checks.append("REGIME_OK")
            else:
                failed_checks.append("REGIME_UNSUITABLE")
            degraded = bool(regime and regime.degraded_factors)
            if degraded:
                risk_flags.extend(regime.degraded_factors)
            total_checks = len(passed_checks) + len(failed_checks)
            observations.append(
                ScreeningObservation(
                    symbol=dataset.symbol,
                    trade_date=indicator.trade_date,
                    investable=not failed_checks,
                    passed_checks=passed_checks,
                    failed_checks=failed_checks,
                    risk_flags=risk_flags,
                    score=round(len(passed_checks) / max(total_checks, 1), 3),
                    degraded=degraded,
                )
            )
        return observations
