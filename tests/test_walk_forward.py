from datetime import date, timedelta
import tempfile
import unittest
from pathlib import Path

from tradingbot.backtest.engine import WalkForwardBacktestEngine
from tradingbot.backtest.execution import BacktestExecutionAssumptions
from tradingbot.core.enums import PeriodType, RegimeLabel
from tradingbot.core.models import (
    FundamentalSnapshot,
    HistoricalFundamentalPoint,
    HistoricalPriceBar,
    HistoricalShareholdingPoint,
    IndicatorSnapshot,
    ResearchDataset,
    ResearchDateRange,
    RegimeObservation,
    ScreeningObservation,
    SignalObservation,
)
from tradingbot.data_ingest.nse_market_curator.artifacts import ArtifactExporter
from tradingbot.data_ingest.nse_market_curator.dataset_builder import DatasetQualityReport
from tradingbot.data_ingest.screener_adapter.history_models import ScreenerHistoricalDataset


class WalkForwardTest(unittest.TestCase):
    def test_backtest_runs_and_exports_expected_files(self) -> None:
        bars = []
        indicators = []
        regimes = []
        screenings = []
        signals = []
        base = date(2024, 1, 1)
        for i in range(320):
            day = base + timedelta(days=i)
            close = 100 + i * 0.4
            bars.append(HistoricalPriceBar("HAL", day, close - 1, close + 1, close - 2, close, 1000 + i, 1000000 + i, 40.0))
            indicators.append(IndicatorSnapshot(symbol="HAL", trade_date=day, values={"atr_14": 2.0, "composite_score": 0.7, "trend_score": 0.8}))
            regimes.append(RegimeObservation(symbol="HAL", trade_date=day, label=RegimeLabel.BULL_TRENDING, confidence=0.8, factors={"benchmark_trend": 0.8}, degraded_factors=[]))
            screenings.append(ScreeningObservation(symbol="HAL", trade_date=day, investable=True, passed_checks=["LIQUIDITY_OK"], failed_checks=[], risk_flags=[], score=1.0, degraded=False))
            signals.append(SignalObservation(symbol="HAL", trade_date=day, state="ENTER", module_scores={"trend": 0.8}, composite_score=0.7, threshold=0.55, reasons=["REGIME_SUPPORTIVE"]))

        dataset = ResearchDataset(
            symbol="HAL",
            benchmark_symbol="NIFTY 50",
            date_range=ResearchDateRange(base, base + timedelta(days=319)),
            price_bars=bars,
            benchmark_bars=bars,
            vix_history={bar.trade_date: 14.0 for bar in bars},
            corporate_actions={},
            event_calendar={},
            screener_history=ScreenerHistoricalDataset(
                symbol="HAL",
                static_pros=[],
                static_cons=[],
                static_metrics={},
                fundamental_points=[
                    HistoricalFundamentalPoint("HAL", "roce", 28.0, date(2023, 3, 31), PeriodType.ANNUAL, "ratios", "annual_report_plus_90d", date(2023, 6, 29))
                ],
                shareholding_points=[
                    HistoricalShareholdingPoint("HAL", "Promoters", 72.0, date(2023, 3, 31), PeriodType.QUARTERLY, "shareholding", "quarterly_result_plus_45d", date(2023, 5, 15))
                ],
                latest_snapshot=FundamentalSnapshot(12.0, 14.0, 1.0, 28.0, 18.0, 0.4, 72.0, 0.0),
            ),
            dataset_report=DatasetQualityReport(
                symbol="HAL",
                first_available_date=base,
                last_available_date=base + timedelta(days=319),
                missing_ranges=[],
                unavailable_factor_families=[],
                assumptions_applied=[],
                degraded_fields=[],
            ),
        )

        engine = WalkForwardBacktestEngine(BacktestExecutionAssumptions())
        result = engine.run(dataset, indicators, regimes, screenings, signals)
        self.assertGreaterEqual(len(result.daily_states), 1)
        self.assertIn("cagr", result.summary.metrics)

        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = ArtifactExporter(Path(tmpdir)).export(result)
            self.assertTrue(Path(manifest.summary_json).exists())
            self.assertTrue(Path(manifest.trades_json).exists())
            self.assertTrue(Path(manifest.summary_markdown).exists())
