from __future__ import annotations

import argparse
import itertools
from collections import Counter
from datetime import date, datetime
from pathlib import Path
import re

from tradingbot.backtest.engine import CandidateResearchEngine
from tradingbot.backtest.execution import BacktestExecutionAssumptions, RejectionProfile
from tradingbot.core.config import load_config
from tradingbot.core.models import ResearchDateRange
from tradingbot.data_ingest.nse_market_curator.artifacts import ArtifactExporter
from tradingbot.data_ingest.nse_market_curator.dataset_builder import ResearchDatasetBuilder
from tradingbot.data_ingest.nselib_adapter.adapter import NseLibAdapter
from tradingbot.data_ingest.screener_adapter.adapter import ScreenerAdapter
from tradingbot.indicators.history import HistoricalIndicatorCalculator
from tradingbot.regime.history import HistoricalRegimeClassifier
from tradingbot.screening.history import HistoricalScreeningEngine
from tradingbot.strategy.master import MasterStrategyEngine


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the phase-2 non-persistent NSE research pipeline.")
    parser.add_argument("--config", default="config/system.yaml")
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--benchmark", default=None)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--artifacts-dir", default=None)
    return parser


def _scope_label(symbols: list[str]) -> str:
    return " + ".join(symbols)


def _scope_status(row: dict) -> str:
    if row["data_problem_symbols"]:
        return "REJECTED_SCOPE"
    if row["gross_edge"] < 0:
        return "RESEARCH_ONLY"
    if row["excluded_symbols"] and len(row["subset"]) <= len(row["excluded_symbols"]):
        return "REJECTED_SCOPE"
    if row["portfolio_readiness_status"] == "PORTFOLIO_READY":
        return "DEPLOYABLE_DEFAULT"
    if row["deployable_benchmark_status"] == "DEPLOYABLE_BENCHMARK_READY":
        return "DEPLOYABLE_BUT_LIMITED"
    return "RESEARCH_ONLY"


def _scope_rank(row: dict) -> tuple[int, float, float, float, float]:
    status_rank = {
        "DEPLOYABLE_DEFAULT": 3,
        "DEPLOYABLE_BUT_LIMITED": 2,
        "RESEARCH_ONLY": 1,
        "REJECTED_SCOPE": 0,
    }
    return (
        status_rank.get(row["scope_status"], 0),
        row["net_edge"],
        row["gross_edge"],
        row["avg_holding_period_days"],
        row["days_with_2plus_positions_pct"],
    )


def write_run_state_summary(path: Path, summary: dict) -> None:
    metrics = summary["metrics"]
    selected_strategy_mix_text = summary.get("selected_strategy_mix_text") or ", ".join(
        f"{name}:{share:.2f}" for name, share in summary.get("selected_strategy_mix", {}).items()
    )
    symbol_recommendation_lines = [
        f"- `{symbol}`: `{recommendation}`"
        for symbol, recommendation in summary.get("symbol_recommendations", {}).items()
    ]
    def _period_line(name: str, label: str) -> str:
        payload = summary.get("period_highlights", {}).get(name, {})
        if not payload:
            return f"- {label}: `n/a`"
        mix = ", ".join(f"{strategy}:{share:.2f}" for strategy, share in payload.get("selected_strategy_mix", {}).items()) or "n/a"
        return (
            f"- {label}: `{payload.get('label', 'n/a')}` | return `{payload.get('return_pct', 0.0):.6f}` | "
            f"trades `{payload.get('trade_count', 0.0)}` | mix `{mix}`"
        )

    lines = [
        "# Current System State",
        "",
        f"- Run timestamp: `{summary['run_timestamp']}`",
        f"- Run ID: `{summary['run_id']}`",
        f"- Universe: `{', '.join(summary['universe'])}`",
        f"- Requested start date: `{summary['requested_start_date']}`",
        f"- Effective start date: `{summary['effective_start_date']}`",
        f"- Analysis end date: `{summary['analysis_end_date']}`",
        f"- Analyzed trading days: `{summary['analyzed_trading_days']}`",
        f"- Analyzed years approx: `{summary['analyzed_years_approx']}`",
        f"- Winning candidate: `{summary['winning_candidate']}`",
        f"- Winning candidate status: `{summary['winning_candidate_status']}`",
        f"- Best gross-edge candidate: `{summary['best_gross_edge_candidate']}`",
        f"- Best net-edge candidate: `{summary['best_net_edge_candidate']}`",
        f"- Best hold-quality candidate: `{summary['best_hold_quality_candidate']}`",
        f"- Lowest drawdown-duration candidate: `{summary['lowest_drawdown_duration_candidate']}`",
        f"- Most promising candidate: `{summary['most_promising_candidate']}`",
        f"- Most promising candidate behavior: `{summary['most_promising_behavior_style']}`",
        f"- Active selector model: `{summary['active_selector_model']}`",
        f"- Current selected HAL strategy: `{summary['current_selected_hal_strategy']}`",
        f"- Current exit policy behavior: `{summary['current_exit_policy_behavior']}`",
        f"- Selected strategy mix: `{selected_strategy_mix_text}`",
        f"- HAL tradable under any candidate: `{summary['hal_tradable_under_any_candidate']}`",
        f"- HAL research status: `{summary['hal_research_status']}`",
        f"- Portfolio readiness status: `{summary['portfolio_readiness_status']}`",
        f"- Deployable benchmark status: `{summary.get('deployable_benchmark_status', 'n/a')}`",
        f"- Default deployable subset: `{summary.get('default_deployable_subset_text', '')}`",
        f"- Closest viability blocker: `{summary['closest_to_viability_metric']}`",
        f"- HAL single-symbol binding blocker: `{summary['hal_single_symbol_binding_blocker']}`",
        f"- Portfolio-ready binding blocker: `{summary['portfolio_ready_binding_blocker']}`",
        f"- Walk-forward confidence: `{summary.get('walk_forward_confidence', 'n/a')}`",
        f"- Behavior style: `{summary['behavior_style']}`",
        f"- Best aligned symbols: `{', '.join(summary['best_aligned_symbols'])}`",
        f"- Top rejection reasons: `{', '.join(summary['top_rejection_reasons'])}`",
        "",
        "## Metrics",
        f"- CAGR: `{metrics.get('cagr', 0.0):.6f}`",
        f"- Sharpe: `{metrics.get('sharpe', 0.0):.6f}`",
        f"- Sortino: `{metrics.get('sortino', 0.0):.6f}`",
        f"- Max drawdown: `{metrics.get('max_drawdown', 0.0):.6f}`",
        f"- Drawdown duration days: `{metrics.get('drawdown_duration_days', 0.0)}`",
        f"- Turnover: `{metrics.get('turnover', 0.0):.6f}`",
        f"- Win rate: `{metrics.get('win_rate', 0.0):.6f}`",
        f"- Payoff ratio: `{metrics.get('payoff_ratio', 0.0):.6f}`",
        f"- Profit factor: `{metrics.get('profit_factor', 0.0):.6f}`",
        f"- Avg holding period days: `{metrics.get('avg_holding_period_days', 0.0):.6f}`",
        f"- Portfolio heat max: `{metrics.get('portfolio_heat_max', 0.0):.6f}`",
        f"- Avg concurrent positions: `{metrics.get('avg_concurrent_positions', 0.0):.6f}`",
        f"- Max concurrent positions used: `{metrics.get('max_concurrent_positions_used', 0.0):.0f}`",
        f"- Days with any position %: `{metrics.get('days_with_any_position_pct', 0.0):.6f}`",
        f"- Days with 2+ positions %: `{metrics.get('days_with_2plus_positions_pct', 0.0):.6f}`",
        f"- Days with 3 positions %: `{metrics.get('days_with_3_positions_pct', 0.0):.6f}`",
        f"- Cash idle %: `{metrics.get('cash_idle_pct', 0.0):.6f}`",
        f"- Average invested capital %: `{metrics.get('average_invested_capital_pct', 0.0):.6f}`",
        "",
        "## Metric Drivers",
        f"- Gross CAGR proxy: `{metrics.get('gross_cagr_proxy', 0.0):.6f}`",
        f"- Gross Sharpe proxy: `{metrics.get('gross_sharpe_proxy', 0.0):.6f}`",
        f"- Gross Sortino proxy: `{metrics.get('gross_sortino_proxy', 0.0):.6f}`",
        f"- Gross profit factor: `{metrics.get('gross_profit_factor', 0.0):.6f}`",
        f"- Gross payoff ratio: `{metrics.get('gross_payoff_ratio', 0.0):.6f}`",
        f"- Median holding period days: `{metrics.get('median_holding_period_days', 0.0)}`",
        f"- P75 holding period days: `{metrics.get('p75_holding_period_days', 0.0)}`",
        f"- Trades under 5d %: `{metrics.get('trades_under_5d_pct', 0.0):.6f}`",
        f"- Profit from 15d+ holds %: `{metrics.get('profit_from_15d_plus_pct', 0.0):.6f}`",
        f"- Entry threshold floor: `{summary['thresholds'].get('entry_score_threshold', 0.0):.6f}`",
        f"- Hold threshold floor: `{summary['thresholds'].get('hold_score_threshold', 0.0):.6f}`",
        f"- Time stop bars: `{summary['thresholds'].get('time_stop_bars', 0)}`",
        f"- ATR stop multiplier: `{summary['thresholds'].get('atr_stop_multiplier', 0.0):.6f}`",
        f"- Slippage bps: `{summary['thresholds'].get('slippage_bps', 0.0):.6f}`",
        f"- STT buy/sell bps: `{summary['thresholds'].get('stt_buy_bps', 0.0):.6f}` / `{summary['thresholds'].get('stt_sell_bps', 0.0):.6f}`",
        "",
        "## Most Promising Candidate",
        f"- Candidate: `{summary['most_promising_candidate']}`",
        f"- Status: `{summary['most_promising_status']}`",
        f"- CAGR: `{summary['most_promising_metrics'].get('cagr', 0.0):.6f}`",
        f"- Sharpe: `{summary['most_promising_metrics'].get('sharpe', 0.0):.6f}`",
        f"- Profit factor: `{summary['most_promising_metrics'].get('profit_factor', 0.0):.6f}`",
        f"- Avg holding days: `{summary['most_promising_metrics'].get('avg_holding_period_days', 0.0):.6f}`",
        f"- Drawdown duration days: `{summary['most_promising_metrics'].get('drawdown_duration_days', 0.0)}`",
        f"- Trades under 5d %: `{summary['most_promising_metrics'].get('trades_under_5d_pct', 0.0):.6f}`",
        f"- Profit from 15d+ holds %: `{summary['most_promising_metrics'].get('profit_from_15d_plus_pct', 0.0):.6f}`",
        "",
        "## Candidate Notes",
        f"- Candidate modules enabled: `{', '.join(summary['enabled_modules'])}`",
        f"- Candidate modules disabled: `{', '.join(summary['disabled_modules'])}`",
        f"- Event drift: `{'on' if summary['module_decisions'].get('event_drift', {}).get('enabled') else 'off'}` because `{summary['module_decisions'].get('event_drift', {}).get('reason', 'n/a')}`",
        f"- Seasonality: `{'on' if summary['module_decisions'].get('seasonality', {}).get('enabled') else 'off'}` because `{summary['module_decisions'].get('seasonality', {}).get('reason', 'n/a')}`",
        f"- Current HAL recommendation: `{summary['current_hal_recommendation']}`",
        f"- Symbol recommendations: `{summary['symbol_recommendations_text']}`",
        *symbol_recommendation_lines,
        "",
        "## Benchmark",
        f"- Benchmark winner scope: `{summary.get('benchmark_winner_scope', 'n/a')}`",
        f"- Strict portfolio-ready scope: `{summary.get('portfolio_ready_scope', 'n/a')}`",
        f"- Excluded symbols: `{', '.join(summary.get('excluded_symbols', []))}`",
        f"- Ghost symbols: `{', '.join(summary.get('ghost_symbols', []))}`",
        f"- Data problem symbols: `{', '.join(summary.get('data_problem_symbols', []))}`",
        f"- Slot block reasons: `{summary.get('slot_block_reasons_text', '')}`",
        f"- Entry blocker leaderboard: `{summary.get('entry_blocker_leaderboard_text', '')}`",
        f"- Allocator blocker leaderboard: `{summary.get('allocator_blocker_leaderboard_text', '')}`",
        f"- Screening pass rates: `{summary.get('screening_pass_rates_text', '')}`",
        f"- Actionable signal rates: `{summary.get('actionable_signal_rates_text', '')}`",
        f"- Trade conversion rates: `{summary.get('trade_conversion_rates_text', '')}`",
        f"- Hard-risk exit rates: `{summary.get('hard_risk_exit_rates_text', '')}`",
        f"- Active per-symbol overrides: `{summary.get('profile_overrides_text', '')}`",
        f"- Deployment bottleneck: `{summary.get('deployment_constraint', 'unknown')}`",
        "",
        "## Baseline Comparison",
        f"- Cash idle delta: `{summary.get('baseline_comparison', {}).get('cash_idle_pct_delta', 0.0):.6f}`",
        f"- Days with any position delta: `{summary.get('baseline_comparison', {}).get('days_with_any_position_pct_delta', 0.0):.6f}`",
        f"- Days with 2+ positions delta: `{summary.get('baseline_comparison', {}).get('days_with_2plus_positions_pct_delta', 0.0):.6f}`",
        f"- Avg holding period delta: `{summary.get('baseline_comparison', {}).get('avg_holding_period_days_delta', 0.0):.6f}`",
        f"- Gross edge delta: `{summary.get('baseline_comparison', {}).get('gross_edge_delta', 0.0):.6f}`",
        f"- Net edge delta: `{summary.get('baseline_comparison', {}).get('net_edge_delta', 0.0):.6f}`",
        f"- Hard-risk exit rate delta: `{summary.get('baseline_comparison', {}).get('hard_risk_exit_rate_delta', 0.0):.6f}`",
        f"- Selector mix delta: `{summary.get('baseline_comparison', {}).get('selector_mix_delta_text', 'n/a')}`",
        "",
        "## Period Highlights",
        _period_line("weekly", "Latest week"),
        _period_line("monthly", "Latest month"),
        _period_line("quarterly", "Latest quarter"),
        _period_line("yearly", "Latest year"),
        _period_line("overall", "Overall"),
        "",
        "## Interpretation",
        *[f"- {line}" for line in summary["interpretation"]],
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _parse_previous_run_state_summary(path: Path) -> dict[str, float] | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")

    def extract(label: str) -> float | None:
        match = re.search(rf"- {re.escape(label)}: `(-?\d+(?:\.\d+)?)`", text)
        return float(match.group(1)) if match else None

    metrics = {
        "cash_idle_pct": extract("Cash idle %"),
        "days_with_any_position_pct": extract("Days with any position %"),
        "days_with_2plus_positions_pct": extract("Days with 2+ positions %"),
        "avg_holding_period_days": extract("Avg holding period days"),
        "gross_cagr_proxy": extract("Gross CAGR proxy"),
        "cagr": extract("CAGR"),
    }
    if all(value is None for value in metrics.values()):
        return None
    return {key: value for key, value in metrics.items() if value is not None}


def build_run_state_summary(result, symbols: list[str], config=None, previous_summary: dict | None = None) -> dict:
    metrics = result.summary.metrics
    requested_start_date = result.dataset_report.get("requested_start_date")
    effective_start_date = result.dataset_report.get("effective_portfolio_start_date", requested_start_date)
    analysis_end_date = result.daily_states[-1].trade_date.isoformat() if result.daily_states else effective_start_date
    analyzed_trading_days = len(result.daily_states)
    analyzed_years_approx = round(analyzed_trading_days / 252.0, 2) if analyzed_trading_days else 0.0
    candidate_results = result.candidate_results or {}
    winning_candidate = metrics.get("winning_candidate")
    winning_payload = candidate_results.get(winning_candidate, {}) if winning_candidate else {}
    most_promising_candidate = metrics.get("most_promising_candidate")
    most_promising_payload = candidate_results.get(most_promising_candidate, {}) if most_promising_candidate else {}
    symbol_recommendations = most_promising_payload.get("symbol_recommendations", {}) or winning_payload.get("symbol_recommendations", {}) or result.dataset_report.get("symbol_recommendations", {})
    complete_symbol_recommendations = {
        symbol: symbol_recommendations.get(symbol, {}).get("recommendation", "no-trade")
        for symbol in symbols
    }
    current_hal_recommendation = symbol_recommendations.get("HAL", {}).get("recommendation", "unknown")
    most_promising_metrics = most_promising_payload.get("metrics", {})
    most_promising_behavior_style = (
        "owner_style_holding"
        if most_promising_metrics.get("avg_holding_period_days", 0.0) >= result.summary.assumptions.get("min_avg_holding_period_days", 0.0)
        else "short_horizon_churn"
    )
    interpretation = []
    if metrics.get("cagr", 0.0) <= 0 or metrics.get("sharpe", 0.0) <= 0:
        interpretation.append("System does not currently have positive edge.")
    else:
        interpretation.append("System currently shows positive edge on reported top-line metrics.")
    if metrics.get("turnover", 0.0) > 150.0:
        interpretation.append("Turnover is too high for the observed return profile.")
    if metrics.get("avg_holding_period_days", 0.0) < 5.0:
        interpretation.append("Holding periods are too short relative to the configured threshold.")
    if str(metrics.get("winning_candidate_status", "")).startswith("REJECTED"):
        interpretation.append("Candidate rejection is functioning and the current winner is not investable.")
    else:
        interpretation.append("At least one candidate survived the current rejection framework.")
    if metrics.get("behavior_style") == "owner_style_holding":
        interpretation.append("Current best candidate is behaving more like ownership than churn.")
    else:
        interpretation.append("Current best candidate is still behaving like short-horizon churn.")
    if most_promising_behavior_style == "owner_style_holding":
        interpretation.append("The most promising HAL candidate is starting to behave like ownership-style holding.")
    if not metrics.get("hal_tradable_under_any_candidate", False):
        interpretation.append(f"HAL is not currently tradable; closest candidate is {most_promising_candidate}.")
    if metrics.get("profit_from_15d_plus_pct", 0.0) <= 0:
        interpretation.append("No meaningful profit is coming from 15d+ winners yet.")
    blocker = metrics.get("closest_to_viability_metric", "unknown")
    blocker_messages = {
        "trade_count_confidence": "Main failure mode is insufficient trade-count confidence.",
        "drawdown_duration_days": "Main failure mode is drawdown-duration persistence.",
        "gross_edge": "Main failure mode is weak gross edge.",
        "avg_holding_period_days": "Main failure mode is insufficient holding quality.",
        "turnover": "Main failure mode is excess turnover.",
    }
    main_failure = blocker_messages.get(blocker, "Main failure mode is weak edge.")
    interpretation.insert(1, main_failure)
    period_summaries = result.period_summaries or {}
    period_highlights = {
        level: payload[-1] if payload else {}
        for level, payload in period_summaries.items()
    }
    selected_strategy_mix = result.dataset_report.get("selected_strategy_mix", {})
    concurrent_usage = result.dataset_report.get("concurrent_usage", {})
    benchmark_scope_results = result.dataset_report.get("benchmark_scope_results", [])
    benchmark_winner_scope = result.dataset_report.get("benchmark_winner_scope", _scope_label(symbols))
    portfolio_ready_scope = result.dataset_report.get("portfolio_ready_scope", "n/a")
    default_subset = result.dataset_report.get("default_deployable_subset", symbols)
    symbol_health = result.dataset_report.get("symbol_recommendations", {})
    excluded_symbols = [symbol for symbol, payload in symbol_health.items() if payload.get("recommendation") == "exclude"]
    ghost_symbols = [symbol for symbol, payload in symbol_health.items() if payload.get("recommendation") == "ghost_no_signals"]
    data_problem_symbols = [symbol for symbol, payload in symbol_health.items() if payload.get("recommendation") == "data_problem"]
    slot_block_reasons = result.dataset_report.get("slot_block_reason_counts", {})
    entry_blockers = result.dataset_report.get("entry_blocker_counts", {})
    screening_pass_rates = {
        symbol: payload.get("screening_pass_rate", 0.0)
        for symbol, payload in symbol_health.items()
    }
    actionable_signal_rates = {
        symbol: payload.get("actionable_signal_rate", 0.0)
        for symbol, payload in symbol_health.items()
    }
    trade_conversion_rates = {
        symbol: payload.get("trade_conversion_rate", 0.0)
        for symbol, payload in symbol_health.items()
    }
    hard_risk_exit_rates = {
        symbol: payload.get("hard_risk_exit_rate", 0.0)
        for symbol, payload in symbol_health.items()
    }
    strategy_deployment_summary = result.dataset_report.get("strategy_deployment_summary", {})
    profile_overrides = {
        symbol: ("strict_quality" if symbol == "HAL" else "relaxed_screening" if symbol == "IRCTC" else "strict_breakout" if symbol == "BSE" else "default")
        for symbol in symbols
    }
    previous_metrics = previous_summary or {}
    gross_edge_delta = metrics.get("gross_cagr_proxy", 0.0) - previous_metrics.get("gross_cagr_proxy", metrics.get("gross_cagr_proxy", 0.0))
    net_edge_delta = metrics.get("cagr", 0.0) - previous_metrics.get("cagr", metrics.get("cagr", 0.0))
    dominant_entry_blocker = next(iter(sorted(entry_blockers.items(), key=lambda item: item[1], reverse=True)), ("unknown", 0))[0]
    deployment_constraint = "gross_edge_protection"
    if dominant_entry_blocker == "REGIME_UNSUITABLE":
        deployment_constraint = "screening"
    elif selected_strategy_mix.get("franchise_pullback_accumulator", 0.0) > 0.70 and metrics.get("gross_cagr_proxy", 0.0) <= 0:
        deployment_constraint = "selector_quality"
    symbol_recommendations_map = complete_symbol_recommendations
    return {
        "run_timestamp": datetime.now().astimezone().isoformat(),
        "run_id": result.summary.run_id,
        "universe": symbols,
        "requested_start_date": requested_start_date,
        "effective_start_date": effective_start_date,
        "analysis_end_date": analysis_end_date,
        "analyzed_trading_days": analyzed_trading_days,
        "analyzed_years_approx": analyzed_years_approx,
        "winning_candidate": winning_candidate,
        "winning_candidate_status": metrics.get("winning_candidate_status"),
        "best_gross_edge_candidate": metrics.get("best_gross_edge_candidate"),
        "best_net_edge_candidate": metrics.get("best_net_edge_candidate"),
        "best_hold_quality_candidate": metrics.get("best_hold_quality_candidate"),
        "lowest_drawdown_duration_candidate": metrics.get("lowest_drawdown_duration_candidate"),
        "most_promising_candidate": most_promising_candidate,
        "most_promising_status": most_promising_payload.get("status", "unknown"),
        "most_promising_behavior_style": most_promising_behavior_style,
        "most_promising_metrics": most_promising_metrics,
        "active_selector_model": metrics.get("active_selector_model", "candidate_rank"),
        "current_selected_hal_strategy": metrics.get("current_selected_hal_strategy", "n/a"),
        "current_exit_policy_behavior": metrics.get("current_exit_policy_behavior", "n/a"),
        "selected_strategy_mix": selected_strategy_mix,
        "selected_strategy_mix_text": ", ".join(f"{name}:{share:.2f}" for name, share in selected_strategy_mix.items()),
        "hal_tradable_under_any_candidate": metrics.get("hal_tradable_under_any_candidate", False),
        "hal_research_status": metrics.get("hal_research_status", "RESEARCH_BLOCKED"),
        "portfolio_readiness_status": metrics.get("portfolio_readiness_status", "PORTFOLIO_BLOCKED"),
        "deployable_benchmark_status": metrics.get("deployable_benchmark_status", "RESEARCH_ONLY"),
        "default_deployable_subset_text": ", ".join(default_subset),
        "closest_to_viability_metric": metrics.get("closest_to_viability_metric", "unknown"),
        "hal_single_symbol_binding_blocker": metrics.get("hal_single_symbol_binding_blocker", "unknown"),
        "portfolio_ready_binding_blocker": metrics.get("portfolio_ready_binding_blocker", "unknown"),
        "walk_forward_confidence": metrics.get("walk_forward_confidence", "unknown"),
        "behavior_style": metrics.get("behavior_style", "short_horizon_churn"),
        "best_aligned_symbols": metrics.get("best_aligned_symbols", []),
        "top_rejection_reasons": most_promising_payload.get("rejection_reasons", [])[:3] or winning_payload.get("rejection_reasons", [])[:3],
        "enabled_modules": most_promising_payload.get("enabled_modules", []) or winning_payload.get("enabled_modules", []),
        "disabled_modules": most_promising_payload.get("disabled_modules", []) or winning_payload.get("disabled_modules", []),
        "symbol_recommendations_text": ", ".join(
            f"{symbol}:{recommendation}"
            for symbol, recommendation in complete_symbol_recommendations.items()
        ),
        "symbol_recommendations": symbol_recommendations_map,
        "current_hal_recommendation": current_hal_recommendation,
        "module_decisions": metrics.get("module_decisions", {}),
        "period_highlights": period_highlights,
        "benchmark_scope_results": benchmark_scope_results,
        "benchmark_winner_scope": benchmark_winner_scope,
        "portfolio_ready_scope": portfolio_ready_scope,
        "excluded_symbols": excluded_symbols,
        "ghost_symbols": ghost_symbols,
        "data_problem_symbols": data_problem_symbols,
        "slot_block_reasons_text": ", ".join(f"{name}:{count}" for name, count in slot_block_reasons.items()),
        "entry_blocker_leaderboard_text": ", ".join(
            f"{name}:{count}" for name, count in sorted(entry_blockers.items(), key=lambda item: item[1], reverse=True)[:5]
        ) if entry_blockers else "",
        "allocator_blocker_leaderboard_text": ", ".join(f"{name}:{count}" for name, count in slot_block_reasons.items()),
        "screening_pass_rates_text": ", ".join(f"{symbol}:{value:.2f}" for symbol, value in screening_pass_rates.items()),
        "actionable_signal_rates_text": ", ".join(f"{symbol}:{value:.2f}" for symbol, value in actionable_signal_rates.items()),
        "trade_conversion_rates_text": ", ".join(f"{symbol}:{value:.2f}" for symbol, value in trade_conversion_rates.items()),
        "hard_risk_exit_rates_text": ", ".join(f"{symbol}:{value:.2f}" for symbol, value in hard_risk_exit_rates.items()),
        "profile_overrides_text": "; ".join(f"{symbol}:{profile_overrides[symbol]}" for symbol in symbols),
        "strategy_deployment_summary": strategy_deployment_summary,
        "deployment_constraint": deployment_constraint,
        "baseline_comparison": {
            "cash_idle_pct_delta": round(metrics.get("cash_idle_pct", 0.0) - previous_metrics.get("cash_idle_pct", metrics.get("cash_idle_pct", 0.0)), 6),
            "days_with_any_position_pct_delta": round(metrics.get("days_with_any_position_pct", 0.0) - previous_metrics.get("days_with_any_position_pct", metrics.get("days_with_any_position_pct", 0.0)), 6),
            "days_with_2plus_positions_pct_delta": round(metrics.get("days_with_2plus_positions_pct", 0.0) - previous_metrics.get("days_with_2plus_positions_pct", metrics.get("days_with_2plus_positions_pct", 0.0)), 6),
            "avg_holding_period_days_delta": round(metrics.get("avg_holding_period_days", 0.0) - previous_metrics.get("avg_holding_period_days", metrics.get("avg_holding_period_days", 0.0)), 6),
            "gross_edge_delta": round(gross_edge_delta, 6),
            "net_edge_delta": round(net_edge_delta, 6),
            "hard_risk_exit_rate_delta": 0.0,
            "selector_mix_delta_text": "n/a",
        },
        "thresholds": {
            "entry_score_threshold": getattr(getattr(config, "strategy", None), "entry_score_threshold", 0.0),
            "hold_score_threshold": getattr(getattr(config, "strategy", None), "hold_score_threshold", 0.0),
            "time_stop_bars": result.summary.assumptions.get("time_stop_bars", 0),
            "atr_stop_multiplier": result.summary.assumptions.get("atr_stop_multiplier", 0.0),
            "slippage_bps": result.summary.assumptions.get("slippage_bps", 0.0),
            "stt_buy_bps": result.summary.assumptions.get("stt_buy_bps", 0.0),
            "stt_sell_bps": result.summary.assumptions.get("stt_sell_bps", 0.0),
        },
        "metrics": {**metrics, **concurrent_usage},
        "interpretation": interpretation[:6],
    }


def build_failed_run_state_summary(symbols: list[str], requested_start_date: str | None, error_message: str, effective_start_date: str | None = None) -> dict:
    interpretation = [
        "Run failed before fresh research metrics were produced.",
        "Current system state should be treated as stale until a successful run completes.",
        f"Latest failure: {error_message}",
    ]
    return {
        "run_timestamp": datetime.now().astimezone().isoformat(),
        "run_id": "FAILED",
        "universe": symbols,
        "requested_start_date": requested_start_date,
        "effective_start_date": effective_start_date or requested_start_date,
        "analysis_end_date": effective_start_date or requested_start_date,
        "analyzed_trading_days": 0,
        "analyzed_years_approx": 0.0,
        "winning_candidate": "n/a",
        "winning_candidate_status": "FAILED",
        "best_gross_edge_candidate": "n/a",
        "best_net_edge_candidate": "n/a",
        "best_hold_quality_candidate": "n/a",
        "lowest_drawdown_duration_candidate": "n/a",
        "most_promising_candidate": "n/a",
        "most_promising_status": "FAILED",
        "most_promising_behavior_style": "unknown",
        "most_promising_metrics": {},
        "active_selector_model": "unknown",
        "current_selected_hal_strategy": "n/a",
        "current_exit_policy_behavior": "n/a",
        "selected_strategy_mix": {},
        "selected_strategy_mix_text": "",
        "hal_tradable_under_any_candidate": False,
        "hal_research_status": "RESEARCH_BLOCKED",
        "portfolio_readiness_status": "PORTFOLIO_BLOCKED",
        "deployable_benchmark_status": "REJECTED_SCOPE",
        "default_deployable_subset_text": ", ".join(symbols),
        "closest_to_viability_metric": "run_failure",
        "hal_single_symbol_binding_blocker": "run_failure",
        "portfolio_ready_binding_blocker": "run_failure",
        "walk_forward_confidence": "unknown",
        "behavior_style": "unknown",
        "best_aligned_symbols": [],
        "top_rejection_reasons": [],
        "enabled_modules": [],
        "disabled_modules": [],
        "symbol_recommendations_text": "",
        "symbol_recommendations": {},
        "current_hal_recommendation": "unknown",
        "module_decisions": {},
        "period_highlights": {},
        "benchmark_scope_results": [],
        "benchmark_winner_scope": "n/a",
        "portfolio_ready_scope": "n/a",
        "excluded_symbols": [],
        "ghost_symbols": [],
        "data_problem_symbols": [],
        "slot_block_reasons_text": "",
        "entry_blocker_leaderboard_text": "",
        "allocator_blocker_leaderboard_text": "",
        "screening_pass_rates_text": "",
        "actionable_signal_rates_text": "",
        "trade_conversion_rates_text": "",
        "hard_risk_exit_rates_text": "",
        "profile_overrides_text": "",
        "thresholds": {
            "entry_score_threshold": 0.0,
            "hold_score_threshold": 0.0,
            "time_stop_bars": 0,
            "atr_stop_multiplier": 0.0,
            "slippage_bps": 0.0,
            "stt_buy_bps": 0.0,
            "stt_sell_bps": 0.0,
        },
        "metrics": {
            "cagr": 0.0,
            "sharpe": 0.0,
            "sortino": 0.0,
            "max_drawdown": 0.0,
            "drawdown_duration_days": 0.0,
            "turnover": 0.0,
            "win_rate": 0.0,
            "payoff_ratio": 0.0,
            "profit_factor": 0.0,
            "avg_holding_period_days": 0.0,
            "portfolio_heat_max": 0.0,
            "avg_concurrent_positions": 0.0,
            "max_concurrent_positions_used": 0.0,
            "days_with_any_position_pct": 0.0,
            "days_with_2plus_positions_pct": 0.0,
            "days_with_3_positions_pct": 0.0,
            "cash_idle_pct": 0.0,
            "average_invested_capital_pct": 0.0,
            "gross_cagr_proxy": 0.0,
            "gross_sharpe_proxy": 0.0,
            "gross_sortino_proxy": 0.0,
            "gross_profit_factor": 0.0,
            "gross_payoff_ratio": 0.0,
            "median_holding_period_days": 0.0,
            "p75_holding_period_days": 0.0,
            "trades_under_5d_pct": 0.0,
            "profit_from_15d_plus_pct": 0.0,
        },
        "interpretation": interpretation,
    }


def main() -> None:
    args = build_argument_parser().parse_args()
    config = load_config(args.config)
    symbols = [args.symbol] if args.symbol else list(config.universe.symbols)
    benchmark_symbol = args.benchmark or config.universe.benchmark_symbol
    end_date = _parse_date(args.end_date) or _parse_date(config.research.end_date) or date.today()
    start_date = _parse_date(args.start_date) or _parse_date(config.research.start_date) or date(2016, 1, 1)
    date_range = ResearchDateRange(start_date=start_date, end_date=end_date)
    summary_skill_path = Path(config.research.summary_skill_path)
    previous_summary = _parse_previous_run_state_summary(summary_skill_path)

    try:
        nse_adapter = NseLibAdapter()
        screener_adapter = ScreenerAdapter(Path.cwd())
        dataset_builder = ResearchDatasetBuilder(nse_adapter, screener_adapter)
        datasets = {}
        indicators = {}
        regimes = {}
        screenings = {}
        signal_candidates: dict[str, dict[str, list]] = {}
        strategy_engine = MasterStrategyEngine(
            entry_threshold_floor=config.strategy.entry_score_threshold,
            hold_threshold_floor=config.strategy.hold_score_threshold,
        )
        for symbol in symbols:
            dataset = dataset_builder.build(symbol=symbol, benchmark_symbol=benchmark_symbol, date_range=date_range)
            symbol_indicators = HistoricalIndicatorCalculator().compute(dataset)
            symbol_regimes = HistoricalRegimeClassifier().classify(dataset, symbol_indicators)
            symbol_screenings = HistoricalScreeningEngine().evaluate(dataset, symbol_indicators, symbol_regimes)
            candidate_signals = strategy_engine.evaluate_candidates(
                dataset=dataset,
                indicators=symbol_indicators,
                regimes=symbol_regimes,
                screenings=symbol_screenings,
                train_years=config.research.train_years,
                test_years=config.research.test_years,
                candidate_set=config.research.candidate_set,
                symbol_profile=(config.universe.symbol_profiles or {}).get(symbol, {}),
                symbol_tags=(config.universe.symbol_profiles or {}).get(symbol, {}).get("tags", []),
            )
            datasets[symbol] = dataset
            indicators[symbol] = symbol_indicators
            regimes[symbol] = symbol_regimes
            screenings[symbol] = symbol_screenings
            for candidate_name, signal_list in candidate_signals.items():
                signal_candidates.setdefault(candidate_name, {})[symbol] = signal_list

        assumptions = BacktestExecutionAssumptions(
            initial_cash=config.portfolio.starting_cash,
            slippage_bps=config.costs.slippage_bps,
            fee_bps=0.0,
            atr_stop_multiplier=config.risk.atr_stop_multiplier,
            time_stop_bars=config.strategy.time_stop_bars,
            brokerage_buy=config.costs.brokerage_buy,
            brokerage_sell=config.costs.brokerage_sell,
            stt_buy_bps=config.costs.stt_buy_bps,
            stt_sell_bps=config.costs.stt_sell_bps,
            exchange_txn_bps=config.costs.exchange_txn_bps,
            sebi_per_crore=config.costs.sebi_per_crore,
            gst_pct=config.costs.gst_pct,
            stamp_buy_bps=config.costs.stamp_buy_bps,
            dp_charge_sell_flat=config.costs.dp_charge_sell_flat,
            impact_model=config.costs.impact_model,
            impact_adv_fraction_cap=config.costs.impact_adv_fraction_cap,
            max_portfolio_heat=config.portfolio.max_heat,
            max_symbol_weight=config.portfolio.max_symbol_weight,
            max_active_positions=config.universe.max_active_positions,
            min_cagr=config.research.rejection.min_cagr,
            min_sharpe=config.research.rejection.min_sharpe,
            min_profit_factor=config.research.rejection.min_profit_factor,
            max_drawdown=config.research.rejection.max_drawdown,
            max_drawdown_duration_days=config.research.rejection.max_drawdown_duration_days,
            max_turnover=config.research.rejection.max_turnover,
            min_avg_holding_period_days=config.research.rejection.min_avg_holding_period_days,
            max_oos_sharpe_drop_pct=config.research.rejection.max_oos_sharpe_drop_pct,
            min_trade_count=config.research.rejection.min_trade_count,
        )
        hal_profile = RejectionProfile(
            min_cagr=config.research.rejection_profiles.hal_single_symbol.min_cagr,
            min_sharpe=config.research.rejection_profiles.hal_single_symbol.min_sharpe,
            min_profit_factor=config.research.rejection_profiles.hal_single_symbol.min_profit_factor,
            max_drawdown=config.research.rejection_profiles.hal_single_symbol.max_drawdown,
            max_drawdown_duration_days=config.research.rejection_profiles.hal_single_symbol.max_drawdown_duration_days,
            max_turnover=config.research.rejection_profiles.hal_single_symbol.max_turnover,
            min_avg_holding_period_days=config.research.rejection_profiles.hal_single_symbol.min_avg_holding_period_days,
            max_oos_sharpe_drop_pct=config.research.rejection_profiles.hal_single_symbol.max_oos_sharpe_drop_pct,
            max_portfolio_heat=config.research.rejection_profiles.hal_single_symbol.max_portfolio_heat,
            min_trade_count=config.research.rejection_profiles.hal_single_symbol.min_trade_count,
        )
        portfolio_profile = RejectionProfile(
            min_cagr=config.research.rejection_profiles.portfolio_multi_symbol.min_cagr,
            min_sharpe=config.research.rejection_profiles.portfolio_multi_symbol.min_sharpe,
            min_profit_factor=config.research.rejection_profiles.portfolio_multi_symbol.min_profit_factor,
            max_drawdown=config.research.rejection_profiles.portfolio_multi_symbol.max_drawdown,
            max_drawdown_duration_days=config.research.rejection_profiles.portfolio_multi_symbol.max_drawdown_duration_days,
            max_turnover=config.research.rejection_profiles.portfolio_multi_symbol.max_turnover,
            min_avg_holding_period_days=config.research.rejection_profiles.portfolio_multi_symbol.min_avg_holding_period_days,
            max_oos_sharpe_drop_pct=config.research.rejection_profiles.portfolio_multi_symbol.max_oos_sharpe_drop_pct,
            max_portfolio_heat=config.research.rejection_profiles.portfolio_multi_symbol.max_portfolio_heat,
            min_trade_count=config.research.rejection_profiles.portfolio_multi_symbol.min_trade_count,
        )
        base_engine = CandidateResearchEngine(
            assumptions,
            hal_rejection_profile=hal_profile,
            portfolio_rejection_profile=portfolio_profile,
        )
        benchmark_profile = RejectionProfile(
            min_cagr=config.research.rejection_profiles.deployable_three_symbol_benchmark.min_cagr,
            min_sharpe=config.research.rejection_profiles.deployable_three_symbol_benchmark.min_sharpe,
            min_profit_factor=config.research.rejection_profiles.deployable_three_symbol_benchmark.min_profit_factor,
            max_drawdown=config.research.rejection_profiles.deployable_three_symbol_benchmark.max_drawdown,
            max_drawdown_duration_days=config.research.rejection_profiles.deployable_three_symbol_benchmark.max_drawdown_duration_days,
            max_turnover=config.research.rejection_profiles.deployable_three_symbol_benchmark.max_turnover,
            min_avg_holding_period_days=config.research.rejection_profiles.deployable_three_symbol_benchmark.min_avg_holding_period_days,
            max_oos_sharpe_drop_pct=config.research.rejection_profiles.deployable_three_symbol_benchmark.max_oos_sharpe_drop_pct,
            max_portfolio_heat=config.research.rejection_profiles.deployable_three_symbol_benchmark.max_portfolio_heat,
            min_trade_count=config.research.rejection_profiles.deployable_three_symbol_benchmark.min_trade_count,
        )

        subsets = [list(combo) for size in range(1, len(symbols) + 1) for combo in itertools.combinations(symbols, size)]
        benchmark_scope_results = []
        benchmark_results_by_label = {}
        for subset in subsets:
            engine = base_engine if len(subset) == 1 else CandidateResearchEngine(
                assumptions,
                hal_rejection_profile=hal_profile,
                portfolio_rejection_profile=benchmark_profile,
            )
            subset_result = engine.run_candidates(
                datasets={symbol: datasets[symbol] for symbol in subset},
                indicators={symbol: indicators[symbol] for symbol in subset},
                regimes={symbol: regimes[symbol] for symbol in subset},
                screenings={symbol: screenings[symbol] for symbol in subset},
                signal_candidates={
                    candidate_name: {symbol: signal_map[symbol] for symbol in subset}
                    for candidate_name, signal_map in signal_candidates.items()
                },
                symbol_profiles={symbol: (config.universe.symbol_profiles or {}).get(symbol, {}) for symbol in subset},
            )
            subset_metrics = subset_result.summary.metrics
            symbol_health = subset_result.dataset_report.get("symbol_recommendations", {})
            excluded_symbols = [symbol for symbol, payload in symbol_health.items() if payload.get("recommendation") == "exclude"]
            ghost_symbols = [symbol for symbol, payload in symbol_health.items() if payload.get("recommendation") == "ghost_no_signals"]
            data_problem_symbols = [symbol for symbol, payload in symbol_health.items() if payload.get("recommendation") == "data_problem"]
            scope_row = {
                "subset": subset,
                "scope_label": _scope_label(subset),
                "candidate_winner": subset_metrics.get("winning_candidate"),
                "deployable_benchmark_status": "DEPLOYABLE_BENCHMARK_READY" if not excluded_symbols and subset_metrics.get("gross_profit_factor", 0.0) >= benchmark_profile.min_profit_factor and subset_metrics.get("gross_cagr_proxy", 0.0) >= benchmark_profile.min_cagr else "RESEARCH_ONLY",
                "portfolio_readiness_status": subset_metrics.get("portfolio_readiness_status", "PORTFOLIO_BLOCKED"),
                "blocker": subset_metrics.get("closest_to_viability_metric"),
                "trade_count": subset_metrics.get("turnover", 0.0),
                "avg_holding_period_days": subset_metrics.get("avg_holding_period_days", 0.0),
                "gross_edge": subset_metrics.get("gross_cagr_proxy", 0.0),
                "net_edge": subset_metrics.get("cagr", 0.0),
                "drawdown_duration_days": subset_metrics.get("drawdown_duration_days", 0.0),
                "avg_concurrent_positions": subset_metrics.get("avg_concurrent_positions", 0.0),
                "max_concurrent_positions_used": subset_metrics.get("max_concurrent_positions_used", 0.0),
                "days_with_2plus_positions_pct": subset_metrics.get("days_with_2plus_positions_pct", 0.0),
                "cash_idle_pct": subset_metrics.get("cash_idle_pct", 0.0),
                "selected_strategy_mix": subset_result.dataset_report.get("selected_strategy_mix", {}),
                "symbol_verdicts": {symbol: payload.get("recommendation", "unknown") for symbol, payload in symbol_health.items()},
                "excluded_symbols": excluded_symbols,
                "ghost_symbols": ghost_symbols,
                "data_problem_symbols": data_problem_symbols,
                "walk_forward_confidence": subset_metrics.get("walk_forward_confidence", "unknown"),
            }
            scope_row["scope_status"] = _scope_status(scope_row)
            benchmark_scope_results.append(scope_row)
            benchmark_results_by_label[scope_row["scope_label"]] = subset_result

        benchmark_scope_results.sort(key=_scope_rank, reverse=True)
        winning_scope = benchmark_scope_results[0]
        live_scope_label = _scope_label(symbols)
        result = benchmark_results_by_label[live_scope_label]
        portfolio_ready_scope = next((row["scope_label"] for row in benchmark_scope_results if row["portfolio_readiness_status"] == "PORTFOLIO_READY"), "n/a")
        result.summary.metrics.update(
            {
                "deployable_benchmark_status": next((row["scope_status"] for row in benchmark_scope_results if row["scope_label"] == live_scope_label), "RESEARCH_ONLY"),
                "walk_forward_confidence": result.candidate_results[result.summary.metrics.get("most_promising_candidate", result.summary.metrics.get("winning_candidate"))]["oos_summary"].get("walk_forward_confidence", "unknown") if result.candidate_results else "unknown",
            }
        )
        result.dataset_report.update(
            {
                "benchmark_scope_results": benchmark_scope_results,
                "benchmark_winner_scope": winning_scope["scope_label"],
                "portfolio_ready_scope": portfolio_ready_scope,
                "default_deployable_subset": symbols,
            }
        )

        artifact_root = Path(args.artifacts_dir or config.research.artifacts_dir)
        manifest = ArtifactExporter(artifact_root).export(result)
        state_summary = build_run_state_summary(result, symbols, config=config, previous_summary=previous_summary)
        write_run_state_summary(summary_skill_path, state_summary)
        label = symbols[0] if len(symbols) == 1 else ",".join(symbols)
        print(f"Research run complete for {label}")
        print(f"Artifacts written to: {artifact_root / manifest.run_id}")
        print(f"Summary JSON: {manifest.summary_json}")
    except Exception as exc:
        failure_summary = build_failed_run_state_summary(
            symbols=symbols,
            requested_start_date=start_date.isoformat(),
            error_message=str(exc),
        )
        write_run_state_summary(summary_skill_path, failure_summary)
        raise


if __name__ == "__main__":
    main()
