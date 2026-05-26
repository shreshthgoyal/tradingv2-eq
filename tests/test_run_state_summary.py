from pathlib import Path
import tempfile
import unittest

from tradingbot.jobs.research_run import build_failed_run_state_summary, write_run_state_summary


class RunStateSummaryTest(unittest.TestCase):
    def test_run_state_summary_renders_current_metrics_markdown(self) -> None:
        summary = {
            "run_timestamp": "2026-05-25T18:00:00+05:30",
            "run_id": "research-portfolio-multi",
            "universe": ["HAL", "BEL"],
            "requested_start_date": "2016-01-01",
            "effective_start_date": "2018-03-28",
            "analysis_end_date": "2026-05-25",
            "analyzed_trading_days": 2010,
            "analyzed_years_approx": 7.98,
            "winning_candidate": "baseline_momentum_quality",
            "winning_candidate_status": "REJECTED_NEGATIVE_EDGE",
            "best_gross_edge_candidate": "franchise_breakout_confirmed",
            "best_net_edge_candidate": "franchise_breakout_confirmed",
            "best_hold_quality_candidate": "franchise_breakout_confirmed",
            "lowest_drawdown_duration_candidate": "franchise_risk_managed",
            "most_promising_candidate": "franchise_breakout_confirmed",
            "most_promising_status": "REJECTED_DRAWDOWN_DURATION",
            "most_promising_behavior_style": "owner_style_holding",
            "most_promising_metrics": {
                "cagr": 0.02,
                "sharpe": 0.6,
                "profit_factor": 1.4,
                "avg_holding_period_days": 8.0,
                "drawdown_duration_days": 80,
                "trades_under_5d_pct": 0.1,
                "profit_from_15d_plus_pct": 0.4,
            },
            "hal_tradable_under_any_candidate": False,
            "closest_to_viability_metric": "drawdown_duration_days",
            "active_selector_model": "adaptive_switch",
            "current_selected_hal_strategy": "franchise_breakout_confirmed",
            "current_exit_policy_behavior": "HOLD_WEAKNESS",
            "selected_strategy_mix": {
                "franchise_breakout_confirmed": 0.62,
                "franchise_pullback_accumulator": 0.28,
                "franchise_risk_managed": 0.10,
            },
            "hal_research_status": "RESEARCH_PROMISING",
            "portfolio_readiness_status": "PORTFOLIO_BLOCKED",
            "hal_single_symbol_binding_blocker": "trade_count_confidence",
            "portfolio_ready_binding_blocker": "drawdown_duration_days",
            "module_decisions": {
                "event_drift": {"enabled": True, "reason": "bounded HAL event window"},
                "seasonality": {"enabled": False, "reason": "not validated"},
            },
            "top_rejection_reasons": ["REJECTED_NEGATIVE_EDGE", "REJECTED_TURNOVER"],
            "enabled_modules": ["trend", "pullback"],
            "disabled_modules": ["seasonality"],
            "symbol_recommendations_text": "HAL:accumulate-only",
            "current_hal_recommendation": "accumulate-only",
            "symbol_recommendations": {
                "HAL": "accumulate-only",
                "IRCTC": "breakout-only",
                "BSE": "retain",
            },
            "entry_blocker_leaderboard_text": "REGIME_UNSUITABLE:120, LIQUIDITY_LOW:45",
            "allocator_blocker_leaderboard_text": "invalid_entry_state:7, no_available_slots:2",
            "screening_pass_rates_text": "HAL:0.42, IRCTC:0.18, BSE:0.27",
            "actionable_signal_rates_text": "HAL:0.06, IRCTC:0.01, BSE:0.03",
            "trade_conversion_rates_text": "HAL:0.55, IRCTC:0.00, BSE:0.21",
            "hard_risk_exit_rates_text": "HAL:0.40, IRCTC:0.00, BSE:0.67",
            "profile_overrides_text": "HAL:strict_quality; IRCTC:relaxed_screening; BSE:strict_breakout",
            "thresholds": {
                "entry_score_threshold": 0.55,
                "hold_score_threshold": 0.45,
                "time_stop_bars": 20,
                "atr_stop_multiplier": 2.0,
                "slippage_bps": 5.0,
                "stt_buy_bps": 10.0,
                "stt_sell_bps": 10.0,
            },
            "metrics": {
                "cagr": -0.01,
                "sharpe": -0.2,
                "sortino": -0.1,
                "max_drawdown": 0.12,
                "drawdown_duration_days": 200,
                "turnover": 288.0,
                "win_rate": 0.24,
                "payoff_ratio": 1.97,
                "profit_factor": 0.61,
                "avg_holding_period_days": 3.8,
                "portfolio_heat_max": 0.60,
                "gross_cagr_proxy": 0.02,
                "gross_sharpe_proxy": 0.4,
                "gross_sortino_proxy": 0.5,
                "gross_profit_factor": 1.1,
                "gross_payoff_ratio": 1.8,
                "median_holding_period_days": 4.0,
                "p75_holding_period_days": 7.0,
                "trades_under_5d_pct": 0.6,
                "profit_from_15d_plus_pct": 0.1,
                "days_with_any_position_pct": 0.18,
                "days_with_3_positions_pct": 0.02,
                "average_invested_capital_pct": 0.24,
            },
            "behavior_style": "short_horizon_churn",
            "best_aligned_symbols": ["HAL", "BEL"],
            "period_highlights": {
                "weekly": {"label": "2026-W21", "return_pct": 0.012, "trade_count": 2, "selected_strategy_mix": {"franchise_breakout_confirmed": 0.7}},
                "monthly": {"label": "2026-05", "return_pct": 0.018, "trade_count": 4, "selected_strategy_mix": {"franchise_breakout_confirmed": 0.65}},
                "quarterly": {"label": "2026-Q2", "return_pct": 0.024, "trade_count": 7, "selected_strategy_mix": {"franchise_breakout_confirmed": 0.61}},
                "yearly": {"label": "2026", "return_pct": 0.031, "trade_count": 11, "selected_strategy_mix": {"franchise_breakout_confirmed": 0.58}},
                "overall": {"label": "full_sample", "return_pct": 0.044, "trade_count": 19, "selected_strategy_mix": {"franchise_breakout_confirmed": 0.55}},
            },
            "interpretation": [
                "System does not currently have positive edge.",
                "Turnover is too high for the observed net returns.",
                "Holding periods are too short.",
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "current-system-state.md"
            write_run_state_summary(target, summary)
            text = target.read_text()
        self.assertIn("research-portfolio-multi", text)
        self.assertIn("REJECTED_NEGATIVE_EDGE", text)
        self.assertIn("System does not currently have positive edge.", text)
        self.assertIn("short_horizon_churn", text)
        self.assertIn("HAL, BEL", text)
        self.assertIn("Gross CAGR proxy", text)
        self.assertIn("Top rejection reasons", text)
        self.assertIn("HAL:accumulate-only", text)
        self.assertIn("Best gross-edge candidate", text)
        self.assertIn("Best net-edge candidate", text)
        self.assertIn("Best hold-quality candidate", text)
        self.assertIn("Lowest drawdown-duration candidate", text)
        self.assertIn("Most promising candidate", text)
        self.assertIn("Most Promising Candidate", text)
        self.assertIn("HAL tradable under any candidate", text)
        self.assertIn("drawdown_duration_days", text)
        self.assertIn("adaptive_switch", text)
        self.assertIn("franchise_breakout_confirmed", text)
        self.assertIn("RESEARCH_PROMISING", text)
        self.assertIn("PORTFOLIO_BLOCKED", text)
        self.assertIn("bounded HAL event window", text)
        self.assertIn("Analysis end date", text)
        self.assertIn("Analyzed trading days", text)
        self.assertIn("Selected strategy mix", text)
        self.assertIn("Latest week", text)
        self.assertIn("Latest month", text)
        self.assertIn("Latest quarter", text)
        self.assertIn("Latest year", text)
        self.assertIn("Overall", text)
        self.assertIn("IRCTC", text)
        self.assertIn("BSE", text)
        self.assertIn("Days with any position %", text)
        self.assertIn("Days with 3 positions %", text)
        self.assertIn("Entry blocker leaderboard", text)
        self.assertIn("Allocator blocker leaderboard", text)
        self.assertIn("Screening pass rates", text)
        self.assertIn("Active per-symbol overrides", text)

    def test_failed_run_state_summary_marks_run_as_failed(self) -> None:
        summary = build_failed_run_state_summary(
            symbols=["HAL", "BEL"],
            requested_start_date="2016-01-01",
            error_message="nselib fetch timed out",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "current-system-state.md"
            write_run_state_summary(target, summary)
            text = target.read_text()
        self.assertIn("FAILED", text)
        self.assertIn("nselib fetch timed out", text)
        self.assertIn("Run failed before fresh research metrics were produced.", text)
