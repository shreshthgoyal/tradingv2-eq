from datetime import date, timedelta
import tempfile
import unittest
from pathlib import Path

from tradingbot.backtest.engine import CandidateResearchEngine
from tradingbot.backtest.execution import BacktestExecutionAssumptions, RejectionProfile
from tradingbot.core.enums import CandidateStatus, PeriodType, RegimeLabel
from tradingbot.core.models import (
    CandidateEvaluation,
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


def _dataset(symbol: str, slope: float):
    bars = []
    indicators = []
    regimes = []
    screenings = []
    base = date(2024, 1, 1)
    for i in range(320):
        day = base + timedelta(days=i)
        close = 100 + i * slope
        bars.append(HistoricalPriceBar(symbol, day, close - 1, close + 1, close - 2, close, 1000 + i, 200000000 + i * 5000, 40.0))
        indicators.append(
            IndicatorSnapshot(
                symbol=symbol,
                trade_date=day,
                values={
                    "atr_14": 2.0,
                    "returns_20d": 0.06,
                    "returns_63d": 0.14,
                    "relative_strength_63d": 0.08,
                    "pullback_zscore": -0.4,
                    "distance_to_sma_20": 0.02,
                    "distance_to_sma_200": 0.11,
                    "realized_vol_20d": 0.22,
                    "turnover_ma_20": 250000000.0,
                    "delivery_ma_20": 42.0,
                    "seasonality_turn_of_month": 0.0,
                    "event_drift_score": 0.2,
                },
            )
        )
        regimes.append(RegimeObservation(symbol=symbol, trade_date=day, label=RegimeLabel.BULL_TRENDING, confidence=0.8, factors={"benchmark_trend": 0.8}, degraded_factors=[]))
        screenings.append(ScreeningObservation(symbol=symbol, trade_date=day, investable=True, passed_checks=["LIQUIDITY_OK"], failed_checks=[], risk_flags=[], score=1.0, degraded=False))

    dataset = ResearchDataset(
        symbol=symbol,
        benchmark_symbol="NIFTY 50",
        date_range=ResearchDateRange(base, base + timedelta(days=319)),
        price_bars=bars,
        benchmark_bars=bars,
        vix_history={bar.trade_date: 14.0 for bar in bars},
        corporate_actions={},
        event_calendar={},
        screener_history=ScreenerHistoricalDataset(
            symbol=symbol,
            static_pros=[],
            static_cons=[],
            static_metrics={},
            fundamental_points=[
                HistoricalFundamentalPoint(symbol, "roce", 28.0, date(2023, 3, 31), PeriodType.ANNUAL, "ratios", "annual_report_plus_90d", date(2023, 6, 29))
            ],
            shareholding_points=[
                HistoricalShareholdingPoint(symbol, "Promoters", 72.0, date(2023, 3, 31), PeriodType.QUARTERLY, "shareholding", "quarterly_result_plus_45d", date(2023, 5, 15))
            ],
            latest_snapshot=FundamentalSnapshot(12.0, 14.0, 1.0, 28.0, 18.0, 0.4, 72.0, 0.0),
        ),
        dataset_report=DatasetQualityReport(
            symbol=symbol,
            first_available_date=base,
            last_available_date=base + timedelta(days=319),
            missing_ranges=[],
            unavailable_factor_families=[],
            assumptions_applied=[],
            degraded_fields=[],
        ),
    )
    signals = [
        SignalObservation(symbol=symbol, trade_date=item.trade_date, state="ENTER", module_scores={"trend": 0.8}, composite_score=0.72, threshold=0.55, reasons=["REGIME_SUPPORTIVE"])
        for item in indicators
    ]
    return dataset, indicators, regimes, screenings, signals


def _staged_signals(symbol: str, indicators: list[IndicatorSnapshot]) -> list[SignalObservation]:
    signals: list[SignalObservation] = []
    for idx, item in enumerate(indicators):
        if idx == 3:
            state = "ENTER_PARTIAL"
            score = 0.86
            reasons = ["HIGH_CONVICTION_ENTRY", "DOMINANT_FRANCHISE"]
        elif idx == 7:
            state = "ADD_PARTIAL"
            score = 0.91
            reasons = ["THESIS_CONFIRMED", "PULLBACK_ACCUMULATION"]
        elif idx == 20:
            state = "REDUCE_PARTIAL"
            score = 0.58
            reasons = ["PROFIT_EXTENSION", "PARTIAL_DE_RISK"]
        elif idx == 35:
            state = "EXIT_FULL"
            score = 0.32
            reasons = ["REGIME_WEAKENING", "EXIT_FULL"]
        else:
            state = "HOLD"
            score = 0.66
            reasons = ["TREND_OWNERSHIP"]
        signals.append(
            SignalObservation(
                symbol=symbol,
                trade_date=item.trade_date,
                state=state,
                module_scores={"trend": 0.8, "ownership_bias": 1.0},
                composite_score=score,
                threshold=0.55,
                reasons=reasons,
            )
        )
    return signals


def _weak_churn_signals(symbol: str, indicators: list[IndicatorSnapshot]) -> list[SignalObservation]:
    signals: list[SignalObservation] = []
    for idx, item in enumerate(indicators):
        if idx % 12 == 2:
            state = "ENTER_PARTIAL"
            score = 0.61
            reasons = ["WEAK_ENTRY"]
        elif idx % 12 == 5:
            state = "EXIT_FULL"
            score = 0.28
            reasons = ["FAST_EXIT"]
        else:
            state = "REJECT"
            score = 0.42
            reasons = ["AWAITING_PERSISTENCE"]
        signals.append(
            SignalObservation(
                symbol=symbol,
                trade_date=item.trade_date,
                state=state,
                module_scores={"trend": 0.5},
                composite_score=score,
                threshold=0.55,
                reasons=reasons,
            )
        )
    return signals


def _selector_signals(symbol: str, indicators: list[IndicatorSnapshot], strategy: str) -> list[SignalObservation]:
    signals: list[SignalObservation] = []
    for idx, item in enumerate(indicators):
        base_scores = {
            "trend": 0.8,
            "long_trend_quality": 0.78,
            "relative_strength": 0.70,
            "breakout_confirmation": 0.72,
            "pullback": 0.42,
            "event_drift": 0.0,
            "risk_penalty": 0.04,
            "regime_gate": 1.0,
            "ownership_bias": 0.76,
        }
        state = "HOLD"
        score = 0.68
        reasons = ["TREND_OWNERSHIP"]
        if idx == 2:
            state = "ENTER_PARTIAL"
            score = 0.86
            reasons = ["HIGH_CONVICTION_ENTRY"]
        elif idx == 6:
            state = "REDUCE_PARTIAL"
            score = 0.57
            reasons = ["SCORE_BELOW_HOLD"]
        elif idx == 9:
            state = "EXIT_FULL"
            score = 0.31
            reasons = ["TIME_STOP"]

        if strategy == "pullback":
            base_scores["breakout_confirmation"] = 0.30
            base_scores["pullback"] = 0.82
            base_scores["relative_strength"] = 0.61
            if idx == 2:
                reasons = ["PULLBACK_ACCUMULATION"]
        elif strategy == "breakout":
            base_scores["breakout_confirmation"] = 0.88
            base_scores["pullback"] = 0.36
        elif strategy == "event":
            base_scores["event_drift"] = 0.42
            base_scores["breakout_confirmation"] = 0.74
            if idx == 2:
                reasons = ["EVENT_DRIFT_SUPPORTIVE"]
        elif strategy == "risk":
            base_scores["risk_penalty"] = 0.16
            base_scores["breakout_confirmation"] = 0.58
            if idx == 6:
                reasons = ["REGIME_NOT_SUPPORTIVE"]

        signals.append(
            SignalObservation(
                symbol=symbol,
                trade_date=item.trade_date,
                state=state,
                module_scores=base_scores,
                composite_score=score,
                threshold=0.55,
                reasons=reasons,
            )
        )
    return signals


class PortfolioResearchTest(unittest.TestCase):
    def test_candidate_research_engine_exports_candidate_artifacts(self) -> None:
        hal = _dataset("HAL", 0.45)
        bel = _dataset("BEL", 0.35)
        engine = CandidateResearchEngine(
            BacktestExecutionAssumptions(
                max_portfolio_heat=0.6,
                max_symbol_weight=0.3,
                max_active_positions=2,
                min_cagr=0.01,
                min_sharpe=0.1,
                min_profit_factor=1.1,
                max_drawdown=0.20,
                max_drawdown_duration_days=120,
                max_turnover=150.0,
                min_avg_holding_period_days=5.0,
                max_oos_sharpe_drop_pct=20.0,
                min_trade_count=5,
            )
        )
        result = engine.run_candidates(
            datasets={"HAL": hal[0], "BEL": bel[0]},
            indicators={"HAL": hal[1], "BEL": bel[1]},
            regimes={"HAL": hal[2], "BEL": bel[2]},
            screenings={"HAL": hal[3], "BEL": bel[3]},
            signal_candidates={
                "baseline": {"HAL": hal[4], "BEL": bel[4]},
                "event_aware": {"HAL": hal[4], "BEL": bel[4]},
            },
        )
        self.assertIn("baseline", result.candidate_results)
        self.assertIn("portfolio_heat_max", result.summary.metrics)
        self.assertIn(result.candidate_results["baseline"]["status"], {
            "REJECTED_NEGATIVE_EDGE",
            "REJECTED_TURNOVER",
            "REJECTED_HOLDING_PERIOD",
            "REJECTED_DRAWDOWN_DURATION",
            "REJECTED_HEAT_BREACH",
            "REJECTED_TOO_FEW_TRADES",
        })
        self.assertIn("rejection_reasons", result.candidate_results["baseline"])
        self.assertIn("effective_start_date", result.candidate_results["baseline"])
        self.assertIn("winning_candidate", result.summary.metrics)
        self.assertIn("best_gross_edge_candidate", result.summary.metrics)
        self.assertIn("best_net_edge_candidate", result.summary.metrics)
        self.assertIn("best_hold_quality_candidate", result.summary.metrics)
        self.assertIn("lowest_drawdown_duration_candidate", result.summary.metrics)
        self.assertIn("most_promising_candidate", result.summary.metrics)
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = ArtifactExporter(Path(tmpdir)).export(result)
            self.assertTrue(Path(manifest.summary_json).exists())
            self.assertTrue((Path(tmpdir) / manifest.run_id / "candidate_results.json").exists())
            self.assertTrue((Path(tmpdir) / manifest.run_id / "candidate_comparison.md").exists())
            self.assertIn("REJECTED", (Path(tmpdir) / manifest.run_id / "candidate_comparison.md").read_text())

    def test_staged_position_run_records_partial_entries_and_symbol_recommendations(self) -> None:
        hal = _dataset("HAL", 0.65)
        bel = _dataset("BEL", 0.45)
        hal_signals = _staged_signals("HAL", hal[1])
        bel_signals = _staged_signals("BEL", bel[1])
        engine = CandidateResearchEngine(
            BacktestExecutionAssumptions(
                max_portfolio_heat=0.6,
                max_symbol_weight=0.3,
                max_active_positions=2,
                min_cagr=-1.0,
                min_sharpe=-1.0,
                min_profit_factor=0.0,
                max_drawdown=1.0,
                max_drawdown_duration_days=1000,
                max_turnover=1000.0,
                min_avg_holding_period_days=0.0,
                max_oos_sharpe_drop_pct=1000.0,
                min_trade_count=1,
            )
        )
        result = engine.run_candidates(
            datasets={"HAL": hal[0], "BEL": bel[0]},
            indicators={"HAL": hal[1], "BEL": bel[1]},
            regimes={"HAL": hal[2], "BEL": bel[2]},
            screenings={"HAL": hal[3], "BEL": bel[3]},
            signal_candidates={
                "franchise_pullback_accumulator": {"HAL": hal_signals, "BEL": bel_signals},
            },
        )

        decisions = [trade.decision.get("decision") for trade in result.trades]
        exit_decisions = [trade.decision.get("exit_decision") for trade in result.trades]
        self.assertIn("ENTER_PARTIAL", decisions)
        self.assertIn("ADD_PARTIAL", decisions)
        self.assertIn("REDUCE_PARTIAL", exit_decisions)
        self.assertIn("tranche_number", result.trades[0].decision)
        self.assertIn("symbol_recommendations", result.candidate_results["franchise_pullback_accumulator"])
        self.assertIn(
            result.candidate_results["franchise_pullback_accumulator"]["symbol_recommendations"]["HAL"]["recommendation"],
            {"retain", "accumulate-only", "breakout-only", "down-rank", "exclude"},
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = ArtifactExporter(Path(tmpdir)).export(result)
            candidate_json = (Path(tmpdir) / manifest.run_id / "candidate_results.json").read_text()
            self.assertIn("symbol_recommendations", candidate_json)

    def test_candidate_summary_surfaces_metric_specific_leaders(self) -> None:
        hal = _dataset("HAL", 0.55)
        engine = CandidateResearchEngine(
            BacktestExecutionAssumptions(
                max_portfolio_heat=0.6,
                max_symbol_weight=0.3,
                max_active_positions=1,
                min_cagr=1.0,
                min_sharpe=1.0,
                min_profit_factor=5.0,
                max_drawdown=0.01,
                max_drawdown_duration_days=1,
                max_turnover=1.0,
                min_avg_holding_period_days=50.0,
                max_oos_sharpe_drop_pct=1.0,
                min_trade_count=50,
            )
        )
        result = engine.run_candidates(
            datasets={"HAL": hal[0]},
            indicators={"HAL": hal[1]},
            regimes={"HAL": hal[2]},
            screenings={"HAL": hal[3]},
            signal_candidates={
                "franchise_pullback_accumulator": {"HAL": _weak_churn_signals("HAL", hal[1])},
                "franchise_breakout_confirmed": {"HAL": _staged_signals("HAL", hal[1])},
            },
            symbol_profiles={"HAL": {"tags": ["dominant_franchise"]}},
        )
        self.assertEqual(result.summary.metrics["winning_candidate"], "franchise_pullback_accumulator")
        self.assertEqual(result.summary.metrics["best_gross_edge_candidate"], "franchise_breakout_confirmed")
        self.assertEqual(result.summary.metrics["best_net_edge_candidate"], "franchise_breakout_confirmed")
        self.assertEqual(result.summary.metrics["best_hold_quality_candidate"], "franchise_breakout_confirmed")
        self.assertEqual(result.summary.metrics["most_promising_candidate"], "franchise_breakout_confirmed")

    def test_hal_adaptive_selector_prefers_breakout_when_confirmation_is_strong(self) -> None:
        hal = _dataset("HAL", 0.55)
        engine = CandidateResearchEngine(
            BacktestExecutionAssumptions(max_active_positions=1),
            hal_rejection_profile=RejectionProfile(min_trade_count=1, max_drawdown_duration_days=9999),
            portfolio_rejection_profile=RejectionProfile(min_trade_count=20, max_drawdown_duration_days=120),
        )
        result = engine.run_candidates(
            datasets={"HAL": hal[0]},
            indicators={"HAL": hal[1]},
            regimes={"HAL": hal[2]},
            screenings={"HAL": hal[3]},
            signal_candidates={
                "franchise_pullback_accumulator": {"HAL": _selector_signals("HAL", hal[1], "pullback")},
                "franchise_breakout_confirmed": {"HAL": _selector_signals("HAL", hal[1], "breakout")},
                "franchise_risk_managed": {"HAL": _selector_signals("HAL", hal[1], "risk")},
                "franchise_event_drift": {"HAL": _selector_signals("HAL", hal[1], "event")},
                "franchise_seasonality_enabled": {"HAL": _selector_signals("HAL", hal[1], "pullback")},
            },
            symbol_profiles={"HAL": {"tags": ["dominant_franchise"]}},
        )
        entry_rows = [row for row in result.signals if row.get("signal_state") == "ENTER_PARTIAL"]
        self.assertTrue(entry_rows)
        self.assertEqual(entry_rows[0]["selected_strategy"], "franchise_breakout_confirmed")
        self.assertEqual(result.summary.metrics["active_selector_model"], "adaptive_switch")

    def test_hal_adaptive_selector_can_choose_pullback_when_breakout_is_weak(self) -> None:
        hal = _dataset("HAL", 0.55)
        engine = CandidateResearchEngine(
            BacktestExecutionAssumptions(max_active_positions=1),
            hal_rejection_profile=RejectionProfile(min_trade_count=1, max_drawdown_duration_days=9999),
            portfolio_rejection_profile=RejectionProfile(min_trade_count=20, max_drawdown_duration_days=120),
        )
        result = engine.run_candidates(
            datasets={"HAL": hal[0]},
            indicators={"HAL": hal[1]},
            regimes={"HAL": hal[2]},
            screenings={"HAL": hal[3]},
            signal_candidates={
                "franchise_pullback_accumulator": {"HAL": _selector_signals("HAL", hal[1], "pullback")},
                "franchise_breakout_confirmed": {"HAL": _weak_churn_signals("HAL", hal[1])},
                "franchise_risk_managed": {"HAL": _selector_signals("HAL", hal[1], "risk")},
                "franchise_event_drift": {"HAL": _selector_signals("HAL", hal[1], "event")},
                "franchise_seasonality_enabled": {"HAL": _selector_signals("HAL", hal[1], "pullback")},
            },
            symbol_profiles={"HAL": {"tags": ["dominant_franchise"]}},
        )
        entry_rows = [row for row in result.signals if row.get("signal_state") == "ENTER_PARTIAL"]
        self.assertTrue(entry_rows)
        self.assertEqual(entry_rows[0]["selected_strategy"], "franchise_pullback_accumulator")

    def test_hal_and_portfolio_rejection_profiles_are_reported_separately(self) -> None:
        hal = _dataset("HAL", 0.55)
        engine = CandidateResearchEngine(
            BacktestExecutionAssumptions(max_active_positions=1),
            hal_rejection_profile=RejectionProfile(
                min_cagr=-1.0,
                min_sharpe=-1.0,
                min_profit_factor=0.0,
                max_drawdown=1.0,
                max_drawdown_duration_days=9999,
                max_turnover=9999.0,
                min_avg_holding_period_days=0.0,
                max_oos_sharpe_drop_pct=1000.0,
                max_portfolio_heat=1.0,
                min_trade_count=1,
            ),
            portfolio_rejection_profile=RejectionProfile(
                min_cagr=0.0,
                min_sharpe=0.0,
                min_profit_factor=1.0,
                max_drawdown=0.2,
                max_drawdown_duration_days=120,
                max_turnover=150.0,
                min_avg_holding_period_days=5.0,
                max_oos_sharpe_drop_pct=20.0,
                max_portfolio_heat=0.60,
                min_trade_count=15,
            ),
        )
        result = engine.run_candidates(
            datasets={"HAL": hal[0]},
            indicators={"HAL": hal[1]},
            regimes={"HAL": hal[2]},
            screenings={"HAL": hal[3]},
            signal_candidates={
                "franchise_breakout_confirmed": {"HAL": _selector_signals("HAL", hal[1], "breakout")},
            },
            symbol_profiles={"HAL": {"tags": ["dominant_franchise"]}},
        )
        payload = result.candidate_results["franchise_breakout_confirmed"]
        self.assertEqual(payload["hal_research_status"], "RESEARCH_PROMISING")
        self.assertEqual(payload["portfolio_readiness_status"], "PORTFOLIO_BLOCKED")
        self.assertIn("hal_single_symbol_binding_blocker", payload)
        self.assertIn("portfolio_ready_binding_blocker", payload)

    def test_adaptive_selector_does_not_fall_back_to_event_without_strong_event_signal(self) -> None:
        hal = _dataset("HAL", 0.55)
        engine = CandidateResearchEngine(
            BacktestExecutionAssumptions(max_active_positions=1),
            hal_rejection_profile=RejectionProfile(min_trade_count=1, max_drawdown_duration_days=9999),
            portfolio_rejection_profile=RejectionProfile(min_trade_count=20, max_drawdown_duration_days=120),
        )
        result = engine.run_candidates(
            datasets={"HAL": hal[0]},
            indicators={"HAL": hal[1]},
            regimes={"HAL": hal[2]},
            screenings={"HAL": hal[3]},
            signal_candidates={
                "franchise_pullback_accumulator": {"HAL": _selector_signals("HAL", hal[1], "pullback")},
                "franchise_breakout_confirmed": {"HAL": _selector_signals("HAL", hal[1], "breakout")},
                "franchise_risk_managed": {"HAL": _selector_signals("HAL", hal[1], "risk")},
                "franchise_event_drift": {"HAL": _selector_signals("HAL", hal[1], "event")},
                "franchise_seasonality_enabled": {"HAL": _selector_signals("HAL", hal[1], "pullback")},
            },
            symbol_profiles={"HAL": {"tags": ["dominant_franchise"]}},
        )
        entry_rows = [row for row in result.signals if row.get("signal_state") == "ENTER_PARTIAL"]
        self.assertTrue(entry_rows)
        self.assertNotEqual(entry_rows[0]["selected_strategy"], "franchise_event_drift")

    def test_adaptive_selector_never_uses_seasonality_as_default_fallback(self) -> None:
        hal = _dataset("HAL", 0.55)
        engine = CandidateResearchEngine(
            BacktestExecutionAssumptions(max_active_positions=1),
            hal_rejection_profile=RejectionProfile(min_trade_count=1, max_drawdown_duration_days=9999),
            portfolio_rejection_profile=RejectionProfile(min_trade_count=20, max_drawdown_duration_days=120),
        )
        result = engine.run_candidates(
            datasets={"HAL": hal[0]},
            indicators={"HAL": hal[1]},
            regimes={"HAL": hal[2]},
            screenings={"HAL": hal[3]},
            signal_candidates={
                "franchise_pullback_accumulator": {"HAL": _weak_churn_signals("HAL", hal[1])},
                "franchise_breakout_confirmed": {"HAL": _weak_churn_signals("HAL", hal[1])},
                "franchise_risk_managed": {"HAL": _weak_churn_signals("HAL", hal[1])},
                "franchise_event_drift": {"HAL": _weak_churn_signals("HAL", hal[1])},
                "franchise_seasonality_enabled": {"HAL": _selector_signals("HAL", hal[1], "pullback")},
            },
            symbol_profiles={"HAL": {"tags": ["dominant_franchise"]}},
        )
        self.assertTrue(result.signals)
        self.assertNotEqual(result.signals[0]["selected_strategy"], "franchise_seasonality_enabled")

    def test_selector_penalizes_pullback_when_breakout_is_actionable_and_pullback_edge_is_weak(self) -> None:
        hal = _dataset("HAL", 0.55)
        engine = CandidateResearchEngine(
            BacktestExecutionAssumptions(max_active_positions=1),
            hal_rejection_profile=RejectionProfile(min_trade_count=1, max_drawdown_duration_days=9999),
            portfolio_rejection_profile=RejectionProfile(min_trade_count=20, max_drawdown_duration_days=120),
        )
        trade_date = hal[1][2].trade_date
        breakout_signal = _selector_signals("HAL", hal[1], "breakout")[2]
        pullback_signal = _selector_signals("HAL", hal[1], "pullback")[2]
        pullback_signal.state = "ENTER_PARTIAL"
        pullback_signal.entry_band = "high_conviction_entry"
        pullback_signal.score_margin = 0.03
        breakout_signal.state = "ENTER_PARTIAL"
        breakout_signal.entry_band = "standard_entry"
        breakout_signal.score_margin = 0.012

        candidate_evaluations = {
            "franchise_breakout_confirmed": CandidateEvaluation(
                name="franchise_breakout_confirmed",
                status=CandidateStatus.ACCEPTED,
                rejection_reasons=[],
                enabled_modules=[],
                disabled_modules=[],
                effective_start_date=trade_date,
                oos_summary={},
                is_summary={},
                metrics={"gross_profit_factor": 1.2},
                window_metrics=[],
                symbol_recommendations={"HAL": {"gross_contribution": 200.0, "hard_risk_exit_rate": 0.2}},
            ),
            "franchise_pullback_accumulator": CandidateEvaluation(
                name="franchise_pullback_accumulator",
                status=CandidateStatus.ACCEPTED,
                rejection_reasons=[],
                enabled_modules=[],
                disabled_modules=[],
                effective_start_date=trade_date,
                oos_summary={},
                is_summary={},
                metrics={"gross_profit_factor": 0.7},
                window_metrics=[],
                symbol_recommendations={"HAL": {"gross_contribution": -150.0, "hard_risk_exit_rate": 0.9}},
            ),
        }

        selected = engine._select_adaptive_strategy(
            {
                "franchise_breakout_confirmed": breakout_signal,
                "franchise_pullback_accumulator": pullback_signal,
            },
            candidate_evaluations,
            position=None,
            bar=hal[0].price_bars[2],
        )

        self.assertEqual(selected["selected_strategy"], "franchise_breakout_confirmed")
        self.assertEqual(selected["candidate_actionability_rank"][1]["candidate"], "franchise_pullback_accumulator")
        self.assertEqual(selected["candidate_actionability_rank"][1]["rejection_reason"], "pullback_gross_edge_penalty")

    def test_three_symbol_adaptive_run_exports_period_summaries(self) -> None:
        hal = _dataset("HAL", 0.55)
        irctc = _dataset("IRCTC", 0.48)
        bse = _dataset("BSE", 0.60)
        engine = CandidateResearchEngine(
            BacktestExecutionAssumptions(max_active_positions=3),
            hal_rejection_profile=RejectionProfile(min_trade_count=10, max_drawdown_duration_days=9999),
            portfolio_rejection_profile=RejectionProfile(min_trade_count=15, max_drawdown_duration_days=120),
        )
        candidates = {
            "franchise_pullback_accumulator": {
                "HAL": _selector_signals("HAL", hal[1], "pullback"),
                "IRCTC": _selector_signals("IRCTC", irctc[1], "pullback"),
                "BSE": _selector_signals("BSE", bse[1], "pullback"),
            },
            "franchise_breakout_confirmed": {
                "HAL": _selector_signals("HAL", hal[1], "breakout"),
                "IRCTC": _selector_signals("IRCTC", irctc[1], "breakout"),
                "BSE": _selector_signals("BSE", bse[1], "breakout"),
            },
            "franchise_risk_managed": {
                "HAL": _selector_signals("HAL", hal[1], "risk"),
                "IRCTC": _selector_signals("IRCTC", irctc[1], "risk"),
                "BSE": _selector_signals("BSE", bse[1], "risk"),
            },
            "franchise_event_drift": {
                "HAL": _selector_signals("HAL", hal[1], "event"),
                "IRCTC": _selector_signals("IRCTC", irctc[1], "event"),
                "BSE": _selector_signals("BSE", bse[1], "event"),
            },
            "franchise_seasonality_enabled": {
                "HAL": _selector_signals("HAL", hal[1], "pullback"),
                "IRCTC": _selector_signals("IRCTC", irctc[1], "pullback"),
                "BSE": _selector_signals("BSE", bse[1], "pullback"),
            },
        }
        result = engine.run_candidates(
            datasets={"HAL": hal[0], "IRCTC": irctc[0], "BSE": bse[0]},
            indicators={"HAL": hal[1], "IRCTC": irctc[1], "BSE": bse[1]},
            regimes={"HAL": hal[2], "IRCTC": irctc[2], "BSE": bse[2]},
            screenings={"HAL": hal[3], "IRCTC": irctc[3], "BSE": bse[3]},
            signal_candidates=candidates,
            symbol_profiles={
                "HAL": {"tags": ["dominant_franchise", "event_heavy"]},
                "IRCTC": {"tags": ["dominant_franchise", "event_heavy"]},
                "BSE": {"tags": ["dominant_franchise", "event_heavy"]},
            },
        )
        self.assertEqual(result.summary.metrics["active_selector_model"], "adaptive_switch")
        self.assertIn("selected_strategy_mix", result.dataset_report)
        self.assertIn("period_summaries", result.dataset_report)
        self.assertIn("weekly", result.dataset_report["period_summaries"])
        self.assertIn("overall", result.dataset_report["period_summaries"])
        self.assertIn("selected_strategy", result.signals[0])
        self.assertIn("exit_policy", result.signals[0])
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = ArtifactExporter(Path(tmpdir)).export(result)
            run_dir = Path(tmpdir) / manifest.run_id
            self.assertTrue((run_dir / "period_summary_weekly.json").exists())
            self.assertTrue((run_dir / "period_summary_monthly.json").exists())
            self.assertTrue((run_dir / "period_summary_quarterly.json").exists())
            self.assertTrue((run_dir / "period_summary_yearly.json").exists())
            self.assertTrue((run_dir / "period_summary_overall.json").exists())
            self.assertTrue((run_dir / "period_summary.md").exists())

    def test_concurrent_allocator_uses_multiple_symbol_slots(self) -> None:
        hal = _dataset("HAL", 0.55)
        irctc = _dataset("IRCTC", 0.52)
        bse = _dataset("BSE", 0.50)
        signals = {
            "franchise_breakout_confirmed": {
                "HAL": _selector_signals("HAL", hal[1], "breakout"),
                "IRCTC": _selector_signals("IRCTC", irctc[1], "breakout"),
                "BSE": _selector_signals("BSE", bse[1], "pullback"),
            },
        }
        engine = CandidateResearchEngine(
            BacktestExecutionAssumptions(max_active_positions=3, max_portfolio_heat=0.6, max_symbol_weight=0.3),
            hal_rejection_profile=RejectionProfile(min_trade_count=1, max_drawdown_duration_days=9999),
            portfolio_rejection_profile=RejectionProfile(min_trade_count=1, max_drawdown_duration_days=9999),
        )
        result = engine.run_candidates(
            datasets={"HAL": hal[0], "IRCTC": irctc[0], "BSE": bse[0]},
            indicators={"HAL": hal[1], "IRCTC": irctc[1], "BSE": bse[1]},
            regimes={"HAL": hal[2], "IRCTC": irctc[2], "BSE": bse[2]},
            screenings={"HAL": hal[3], "IRCTC": irctc[3], "BSE": bse[3]},
            signal_candidates=signals,
            symbol_profiles={
                "HAL": {"tags": ["dominant_franchise"]},
                "IRCTC": {"tags": ["dominant_franchise"]},
                "BSE": {"tags": ["dominant_franchise"]},
            },
        )
        self.assertGreaterEqual(result.summary.metrics.get("max_concurrent_positions_used", 0), 2)
        self.assertGreater(result.summary.metrics.get("days_with_2plus_positions_pct", 0.0), 0.0)
        self.assertGreater(result.summary.metrics.get("days_with_any_position_pct", 0.0), 0.0)
        self.assertGreater(result.summary.metrics.get("days_with_3_positions_pct", 0.0), 0.0)
        self.assertIn("slot_block_reason_counts", result.dataset_report)
        self.assertIn("deployment_summary", result.dataset_report)
        signal_row = result.signals[0]
        self.assertIn("screening_pass", signal_row)
        self.assertIn("selected_signal_state", signal_row)
        self.assertIn("entry_band", signal_row)
        self.assertIn("allocator_rank", signal_row)
        self.assertIn("slot_awarded", signal_row)

    def test_symbol_health_classifies_ghost_and_exclude(self) -> None:
        hal = _dataset("HAL", 0.55)
        irctc = _dataset("IRCTC", 0.48)
        bse = _dataset("BSE", -0.20)
        ghost_signals = [SignalObservation(symbol="IRCTC", trade_date=item.trade_date, state="REJECT", module_scores={"trend": 0.3}, composite_score=0.2, threshold=0.55, reasons=["SCREENING_BLOCKED"]) for item in irctc[1]]
        bse_bad = [
            SignalObservation(
                symbol="BSE",
                trade_date=item.trade_date,
                state="ENTER_PARTIAL" if idx == 2 else "EXIT_FULL" if idx == 5 else "REJECT",
                module_scores={"trend": 0.4},
                composite_score=0.62 if idx == 2 else 0.25 if idx == 5 else 0.20,
                threshold=0.55,
                reasons=["WEAK_ENTRY"] if idx == 2 else ["REGIME_NOT_SUPPORTIVE"] if idx == 5 else ["AWAITING_PERSISTENCE"],
            )
            for idx, item in enumerate(bse[1])
        ]
        engine = CandidateResearchEngine(
            BacktestExecutionAssumptions(max_active_positions=3),
            hal_rejection_profile=RejectionProfile(min_trade_count=1, max_drawdown_duration_days=9999),
            portfolio_rejection_profile=RejectionProfile(min_trade_count=1, max_drawdown_duration_days=9999),
        )
        result = engine.run_candidates(
            datasets={"HAL": hal[0], "IRCTC": irctc[0], "BSE": bse[0]},
            indicators={"HAL": hal[1], "IRCTC": irctc[1], "BSE": bse[1]},
            regimes={"HAL": hal[2], "IRCTC": irctc[2], "BSE": bse[2]},
            screenings={"HAL": hal[3], "IRCTC": irctc[3], "BSE": bse[3]},
            signal_candidates={
                "franchise_pullback_accumulator": {
                    "HAL": _selector_signals("HAL", hal[1], "breakout"),
                    "IRCTC": ghost_signals,
                    "BSE": bse_bad,
                },
            },
            symbol_profiles={
                "HAL": {"tags": ["dominant_franchise"]},
                "IRCTC": {"tags": ["dominant_franchise"]},
                "BSE": {"tags": ["dominant_franchise"]},
            },
        )
        recs = result.dataset_report["symbol_recommendations"]
        self.assertIn(recs["IRCTC"]["recommendation"], {"ghost_no_signals", "data_problem"})
        self.assertEqual(recs["BSE"]["recommendation"], "exclude")
        self.assertIn(recs["IRCTC"]["repair_mode"], {"threshold_relaxation_needed", "data_problem"})
        self.assertIn(recs["BSE"]["repair_mode"], {"stop_too_tight", "selector_misalignment", "true_no_fit"})
        self.assertIn("screening_pass_rate", recs["HAL"])
        self.assertIn("actionable_signal_rate", recs["HAL"])
        self.assertIn("trade_conversion_rate", recs["HAL"])
        self.assertIn("hard_risk_exit_rate", recs["HAL"])
