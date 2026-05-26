from __future__ import annotations

import pandas as pd

from tradingbot.core.enums import RegimeLabel
from tradingbot.core.models import IndicatorSnapshot, RegimeObservation, ResearchDataset


class HistoricalRegimeClassifier:
    def classify(self, dataset: ResearchDataset, indicators: list[IndicatorSnapshot]) -> list[RegimeObservation]:
        benchmark_bars = sorted(dataset.benchmark_bars, key=lambda item: item.trade_date)
        if not benchmark_bars:
            return []
        indicator_map = {item.trade_date: item for item in indicators}
        benchmark_frame = pd.DataFrame(
            {
                "trade_date": [bar.trade_date for bar in benchmark_bars],
                "close": [bar.close for bar in benchmark_bars],
            }
        ).set_index("trade_date")
        benchmark_frame["sma_50"] = benchmark_frame["close"].rolling(50, min_periods=10).mean()
        benchmark_frame["sma_200"] = benchmark_frame["close"].rolling(200, min_periods=20).mean()
        benchmark_frame["returns_63d"] = benchmark_frame["close"].pct_change(63).fillna(0.0)
        benchmark_frame["slope_50"] = benchmark_frame["sma_50"].diff(20).fillna(0.0)

        observations: list[RegimeObservation] = []
        for trade_date, row in benchmark_frame.iterrows():
            degraded_factors: list[str] = []
            trend_factor = 0.8 if row["close"] >= row["sma_200"] else 0.25
            strength_factor = min(max((row["returns_63d"] + 0.15) / 0.30, 0.0), 1.0)
            slope_factor = 0.7 if row["slope_50"] >= 0 else 0.3
            vix_value = dataset.vix_history.get(trade_date)
            if vix_value is None:
                volatility_factor = 0.5
                degraded_factors.append("vix")
            else:
                volatility_factor = 0.8 if vix_value < 18 else 0.55 if vix_value < 22 else 0.2
            symbol_indicator = indicator_map.get(trade_date)
            if symbol_indicator is None:
                delivery_factor = 0.5
                degraded_factors.append("delivery")
            else:
                delivery_ma = symbol_indicator.values.get("delivery_ma_20", 0.0)
                delivery_factor = min(max(delivery_ma / 50.0, 0.0), 1.0)
            factors = {
                "benchmark_trend": round(trend_factor, 3),
                "benchmark_strength": round(strength_factor, 3),
                "slope_50": round(slope_factor, 3),
                "volatility": round(volatility_factor, 3),
                "delivery_conviction": round(delivery_factor, 3),
            }
            confidence = round(sum(factors.values()) / len(factors), 3)
            if trend_factor >= 0.6 and strength_factor >= 0.55 and volatility_factor >= 0.5:
                label = RegimeLabel.BULL_TRENDING
            elif trend_factor >= 0.6:
                label = RegimeLabel.BULL_RANGING
            elif volatility_factor <= 0.35 or strength_factor <= 0.35:
                label = RegimeLabel.BEAR_TRENDING
            else:
                label = RegimeLabel.BEAR_RANGING
            observations.append(
                RegimeObservation(
                    symbol=dataset.symbol,
                    trade_date=trade_date,
                    label=label,
                    confidence=confidence,
                    factors=factors,
                    degraded_factors=degraded_factors,
                )
            )
        return observations
