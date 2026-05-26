from datetime import date, timedelta
import unittest

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
)
from tradingbot.data_ingest.nse_market_curator.dataset_builder import DatasetQualityReport
from tradingbot.data_ingest.screener_adapter.history_models import ScreenerHistoricalDataset
from tradingbot.strategy.master import MasterStrategyEngine


def _hal_dataset():
    base = date(2024, 1, 1)
    bars = []
    indicators = []
    regimes = []
    screenings = []
    for idx in range(12):
        day = base + timedelta(days=idx)
        close = 100 + idx
        bars.append(HistoricalPriceBar("HAL", day, close - 1, close + 1, close - 2, close, 100000, 250000000.0, 45.0))
        values = {
            "atr_14": 2.0,
            "returns_20d": 0.08 if idx != 5 else 0.0,
            "returns_63d": 0.18,
            "relative_strength_63d": 0.11 if idx != 5 else 0.06,
            "pullback_zscore": -0.35,
            "distance_to_sma_20": 0.03 if idx != 5 else 0.0,
            "distance_to_sma_50": 0.08,
            "distance_to_sma_200": 0.14,
            "realized_vol_20d": 0.20,
            "turnover_ma_20": 350000000.0,
            "delivery_ma_20": 44.0,
            "breakout_distance": 0.06 if idx != 5 else 0.015,
            "event_drift_score": 0.1,
            "seasonality_turn_of_month": 0.0,
            "seasonality_month_of_year": 0.0,
        }
        indicators.append(IndicatorSnapshot(symbol="HAL", trade_date=day, values=values))
        regimes.append(
            RegimeObservation(
                symbol="HAL",
                trade_date=day,
                label=RegimeLabel.BULL_TRENDING,
                confidence=0.8,
                factors={"benchmark_trend": 0.8},
                degraded_factors=[],
            )
        )
        screenings.append(
            ScreeningObservation(
                symbol="HAL",
                trade_date=day,
                investable=True,
                passed_checks=["LIQUIDITY_OK"],
                failed_checks=[],
                risk_flags=[],
                score=1.0,
                degraded=False,
            )
        )

    dataset = ResearchDataset(
        symbol="HAL",
        benchmark_symbol="NIFTY 50",
        date_range=ResearchDateRange(base, base + timedelta(days=11)),
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
            last_available_date=base + timedelta(days=11),
            missing_ranges=[],
            unavailable_factor_families=[],
            assumptions_applied=[],
            degraded_fields=[],
        ),
    )
    return dataset, indicators, regimes, screenings


class HalMasterStrategyTest(unittest.TestCase):
    def test_breakout_candidate_holds_through_minor_early_dip(self) -> None:
        dataset, indicators, regimes, screenings = _hal_dataset()
        engine = MasterStrategyEngine(entry_threshold_floor=0.55, hold_threshold_floor=0.45)

        signals = engine.evaluate_candidates(
            dataset=dataset,
            indicators=indicators,
            regimes=regimes,
            screenings=screenings,
            train_years=3,
            test_years=1,
            symbol_tags=["dominant_franchise"],
        )["franchise_breakout_confirmed"]

        states_by_day = {signal.trade_date: signal.state for signal in signals}
        self.assertEqual(states_by_day[date(2024, 1, 4)], "ENTER_PARTIAL")
        self.assertEqual(states_by_day[date(2024, 1, 6)], "HOLD")

    def test_symbol_profile_relaxes_soft_screening_blockers_without_forcing_reject(self) -> None:
        dataset, indicators, regimes, screenings = _hal_dataset()
        for indicator in indicators:
            indicator.values["turnover_ma_20"] = 90000000.0
            indicator.values["delivery_ma_20"] = 23.0
        for screening in screenings:
            screening.investable = False
            screening.passed_checks = ["VOLATILITY_OK", "GAP_RISK_OK", "EVENT_WINDOW_OK", "PROMOTER_PLEDGE_OK", "FUNDAMENTAL_FLOOR_OK", "RELATIVE_STRENGTH_OK", "REGIME_OK"]
            screening.failed_checks = ["LIQUIDITY_LOW", "DELIVERY_LOW"]

        engine = MasterStrategyEngine(entry_threshold_floor=0.55, hold_threshold_floor=0.45)
        signals = engine.evaluate_candidates(
            dataset=dataset,
            indicators=indicators,
            regimes=regimes,
            screenings=screenings,
            train_years=3,
            test_years=1,
            symbol_profile={
                "tags": ["dominant_franchise"],
                "screening": {
                    "min_turnover_ma_20": 80000000.0,
                    "min_delivery_ratio": 20.0,
                },
                "strategy": {
                    "entry_persistence": 2,
                    "entry_score_offset": -0.02,
                },
            },
        )["franchise_breakout_confirmed"]

        actionable = [signal for signal in signals if signal.state in {"ENTER_PARTIAL", "HOLD"}]
        self.assertTrue(actionable)
        self.assertTrue(all(signal.screening_pass for signal in actionable))
        self.assertIn("LIQUIDITY_LOW", actionable[0].soft_blockers)
        self.assertIn("DELIVERY_LOW", actionable[0].soft_blockers)
        self.assertNotIn("LIQUIDITY_LOW", actionable[0].screening_blockers)
        self.assertIn(actionable[0].entry_band, {"high_conviction_entry", "standard_entry", "watchlist_hold"})

    def test_soft_penalty_regime_can_allow_standard_entry(self) -> None:
        dataset, indicators, regimes, screenings = _hal_dataset()
        for idx, regime in enumerate(regimes):
            regime.label = RegimeLabel.BEAR_RANGING
            regime.degraded_factors = ["benchmark_softening"]
            indicators[idx].values["returns_20d"] = 0.09
            indicators[idx].values["relative_strength_63d"] = 0.12
            indicators[idx].values["breakout_distance"] = 0.065

        engine = MasterStrategyEngine(entry_threshold_floor=0.55, hold_threshold_floor=0.45)
        signals = engine.evaluate_candidates(
            dataset=dataset,
            indicators=indicators,
            regimes=regimes,
            screenings=screenings,
            train_years=3,
            test_years=1,
            symbol_profile={
                "tags": ["dominant_franchise"],
                "strategy": {
                    "entry_persistence": 2,
                    "entry_score_offset": -0.02,
                    "min_breakout_confirmation": 0.58,
                },
            },
        )["franchise_breakout_confirmed"]

        standard_entries = [signal for signal in signals if signal.entry_band == "standard_entry"]
        self.assertTrue(standard_entries)
        self.assertTrue(all(signal.state == "ENTER_PARTIAL" for signal in standard_entries))
        self.assertTrue(all("REGIME_SOFT_PENALTY" in signal.reasons for signal in standard_entries))

    def test_hard_bearish_regime_still_blocks_entries(self) -> None:
        dataset, indicators, regimes, screenings = _hal_dataset()
        for regime in regimes:
            regime.label = RegimeLabel.BEAR_TRENDING
            regime.degraded_factors = ["benchmark_breakdown"]

        engine = MasterStrategyEngine(entry_threshold_floor=0.55, hold_threshold_floor=0.45)
        signals = engine.evaluate_candidates(
            dataset=dataset,
            indicators=indicators,
            regimes=regimes,
            screenings=screenings,
            train_years=3,
            test_years=1,
            symbol_tags=["dominant_franchise"],
        )["franchise_breakout_confirmed"]

        self.assertTrue(signals)
        self.assertTrue(all(signal.state == "REJECT" for signal in signals))
        self.assertTrue(all("REGIME_UNSUITABLE" in signal.screening_blockers for signal in signals))
