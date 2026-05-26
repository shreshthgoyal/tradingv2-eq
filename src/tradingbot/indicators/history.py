from __future__ import annotations

import calendar

import pandas as pd

from tradingbot.core.models import IndicatorSnapshot, ResearchDataset


class HistoricalIndicatorCalculator:
    def compute(self, dataset: ResearchDataset) -> list[IndicatorSnapshot]:
        bars = sorted(dataset.price_bars, key=lambda item: item.trade_date)
        benchmark_bars = sorted(dataset.benchmark_bars, key=lambda item: item.trade_date)
        if not bars:
            return []
        frame = pd.DataFrame(
            {
                "trade_date": [bar.trade_date for bar in bars],
                "open": [bar.open for bar in bars],
                "high": [bar.high for bar in bars],
                "low": [bar.low for bar in bars],
                "close": [bar.close for bar in bars],
                "volume": [bar.volume for bar in bars],
                "turnover": [bar.turnover for bar in bars],
                "delivery_pct": [bar.delivery_pct for bar in bars],
            }
        ).set_index("trade_date")
        frame = frame.sort_index().groupby(level=0).last()
        benchmark_frame = pd.DataFrame(
            {
                "trade_date": [bar.trade_date for bar in benchmark_bars],
                "benchmark_close": [bar.close for bar in benchmark_bars],
            }
        ).set_index("trade_date")
        benchmark_frame = benchmark_frame.sort_index().groupby(level=0).last()
        benchmark_frame = benchmark_frame.reindex(frame.index).ffill()

        returns_1d = frame["close"].pct_change()
        returns_20d = frame["close"].pct_change(20)
        returns_63d = frame["close"].pct_change(63)
        benchmark_returns_63d = benchmark_frame["benchmark_close"].pct_change(63)
        true_range = pd.concat(
            [
                frame["high"] - frame["low"],
                (frame["high"] - frame["close"].shift(1)).abs(),
                (frame["low"] - frame["close"].shift(1)).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr_14 = true_range.rolling(14, min_periods=5).mean()
        sma_20 = frame["close"].rolling(20, min_periods=5).mean()
        sma_50 = frame["close"].rolling(50, min_periods=10).mean()
        sma_200 = frame["close"].rolling(200, min_periods=20).mean()
        close_std_20 = frame["close"].rolling(20, min_periods=5).std().fillna(0.0)
        realized_vol_20d = returns_1d.rolling(20, min_periods=5).std().fillna(0.0) * (252**0.5)
        turnover_ma_20 = frame["turnover"].rolling(20, min_periods=5).mean()
        delivery_ma_20 = frame["delivery_pct"].rolling(20, min_periods=5).mean()
        volume_ma_20 = frame["volume"].rolling(20, min_periods=5).mean()
        pullback_z = ((frame["close"] - sma_20) / close_std_20.replace(0.0, pd.NA)).fillna(0.0)
        breakout_distance = (frame["close"] / frame["close"].rolling(63, min_periods=20).max() - 1.0).fillna(0.0)
        seasonality_turn_of_month = pd.Series(
            [
                1.0
                if trade_date.day >= calendar.monthrange(trade_date.year, trade_date.month)[1] - 2 or trade_date.day <= 3
                else 0.0
                for trade_date in frame.index
            ],
            index=frame.index,
        )
        seasonality_month_of_year = pd.Series(
            [1.0 if trade_date.month in {10, 11, 12} else 0.0 for trade_date in frame.index],
            index=frame.index,
        )
        event_dates = set(dataset.event_calendar.keys())
        event_drift_score = pd.Series(
            [0.2 if trade_date in event_dates else 0.0 for trade_date in frame.index],
            index=frame.index,
        )

        snapshots: list[IndicatorSnapshot] = []
        for trade_date in frame.index:
            close = float(frame.at[trade_date, "close"])
            values = {
                "returns_20d": float(returns_20d.get(trade_date, 0.0) or 0.0),
                "returns_63d": float(returns_63d.get(trade_date, 0.0) or 0.0),
                "benchmark_returns_63d": float(benchmark_returns_63d.get(trade_date, 0.0) or 0.0),
                "relative_strength_63d": float(
                    (returns_63d.get(trade_date, 0.0) or 0.0) - (benchmark_returns_63d.get(trade_date, 0.0) or 0.0)
                ),
                "atr_14": float(atr_14.get(trade_date, 0.0) or 0.0),
                "sma_20": float(sma_20.get(trade_date, close) or close),
                "sma_50": float(sma_50.get(trade_date, close) or close),
                "sma_200": float(sma_200.get(trade_date, close) or close),
                "distance_to_sma_20": float(close / max(float(sma_20.get(trade_date, close) or close), 1.0) - 1.0),
                "distance_to_sma_50": float(close / max(float(sma_50.get(trade_date, close) or close), 1.0) - 1.0),
                "distance_to_sma_200": float(close / max(float(sma_200.get(trade_date, close) or close), 1.0) - 1.0),
                "realized_vol_20d": float(realized_vol_20d.get(trade_date, 0.0) or 0.0),
                "turnover_ma_20": float(turnover_ma_20.get(trade_date, 0.0) or 0.0),
                "delivery_ma_20": float(delivery_ma_20.get(trade_date, 0.0) or 0.0),
                "volume_ma_20": float(volume_ma_20.get(trade_date, 0.0) or 0.0),
                "pullback_zscore": float(pullback_z.get(trade_date, 0.0) or 0.0),
                "breakout_distance": float(breakout_distance.get(trade_date, 0.0) or 0.0),
                "seasonality_turn_of_month": float(seasonality_turn_of_month.get(trade_date, 0.0) or 0.0),
                "seasonality_month_of_year": float(seasonality_month_of_year.get(trade_date, 0.0) or 0.0),
                "event_drift_score": float(event_drift_score.get(trade_date, 0.0) or 0.0),
            }
            snapshots.append(IndicatorSnapshot(symbol=dataset.symbol, trade_date=trade_date, values=values))
        return snapshots
