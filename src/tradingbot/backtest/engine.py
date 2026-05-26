from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from math import sqrt
from types import SimpleNamespace

from tradingbot.backtest.execution import BacktestExecutionAssumptions, CostModel, RejectionProfile
from tradingbot.core.enums import CandidateStatus, DecisionType
from tradingbot.core.models import (
    BacktestDailyState,
    BacktestSummary,
    BacktestTrade,
    CandidateEvaluation,
    ResearchDataset,
    WindowMetrics,
)


@dataclass(slots=True)
class BacktestResult:
    summary: BacktestSummary
    trades: list[BacktestTrade]
    daily_states: list[BacktestDailyState]
    signals: list[dict]
    dataset_report: dict
    candidate_results: dict[str, dict] | None = None
    period_summaries: dict[str, object] | None = None


class WalkForwardBacktestEngine:
    def __init__(self, assumptions: BacktestExecutionAssumptions) -> None:
        self.assumptions = assumptions
        self.cost_model = CostModel(assumptions)

    def run(self, dataset: ResearchDataset, indicators, regimes, screenings, signals) -> BacktestResult:
        bars = sorted(dataset.price_bars, key=lambda item: item.trade_date)
        indicator_map = {item.trade_date: item for item in indicators}
        regime_map = {item.trade_date: item for item in regimes}
        screening_map = {item.trade_date: item for item in screenings}
        signal_map = {item.trade_date: item for item in signals}

        cash = self.assumptions.initial_cash
        quantity = 0
        entry_index = -1
        trailing_stop = 0.0
        highest_close = 0.0
        trades: list[BacktestTrade] = []
        daily_states: list[BacktestDailyState] = []
        signal_rows: list[dict] = []
        nav_series: list[float] = []
        heat_series: list[float] = []
        return_series: list[float] = []
        previous_nav = cash

        for idx, bar in enumerate(bars):
            indicator = indicator_map.get(bar.trade_date)
            regime = regime_map.get(bar.trade_date)
            screening = screening_map.get(bar.trade_date)
            signal = signal_map.get(bar.trade_date)
            next_bar = bars[idx + 1] if idx + 1 < len(bars) else None
            atr = self._indicator_value(indicator, "atr_14", max(bar.high - bar.low, bar.close * 0.02))

            if quantity > 0:
                highest_close = max(highest_close, bar.close)
                trailing_stop = max(trailing_stop, highest_close - (atr * self.assumptions.atr_stop_multiplier))

            signal_rows.append(self._signal_payload(dataset, bar, indicator, regime, screening, signal, cash, quantity, trailing_stop))

            if quantity > 0:
                exit_reason = None
                if bar.close <= trailing_stop:
                    exit_reason = "STOP_TRIGGERED"
                elif signal and str(signal.state) in {"EXIT", "EXIT_FULL"}:
                    exit_reason = "SIGNAL_EXIT"
                elif entry_index >= 0 and idx - entry_index >= self.assumptions.time_stop_bars:
                    exit_reason = "TIME_STOP"
                if exit_reason and next_bar is not None:
                    trade_cost = self.cost_model.apply(next_bar.open, quantity, "sell", adv_turnover=max(bar.turnover, 1.0))
                    cash += quantity * trade_cost.effective_price
                    self._close_latest_trade(trades, next_bar.trade_date, trade_cost.effective_price, exit_reason, trade_cost.total_cost)
                    quantity = 0
                    entry_index = -1
                    trailing_stop = 0.0
                    highest_close = 0.0

            if quantity == 0 and next_bar is not None and self._can_enter(screening, signal):
                notional_cap = cash * min(self.assumptions.max_portfolio_heat, 0.95)
                raw_qty = int(min(notional_cap, cash) / max(next_bar.open, 1.0))
                if raw_qty > 0:
                    trade_cost = self.cost_model.apply(next_bar.open, raw_qty, "buy", adv_turnover=max(bar.turnover, 1.0))
                    quantity = raw_qty
                    cash -= quantity * trade_cost.effective_price
                    entry_index = idx + 1
                    highest_close = bar.close
                    trailing_stop = trade_cost.effective_price - (atr * self.assumptions.atr_stop_multiplier)
                    trades.append(
                        BacktestTrade(
                            symbol=dataset.symbol,
                            entry_date=next_bar.trade_date,
                            exit_date=None,
                            entry_price=trade_cost.effective_price,
                            exit_price=None,
                            quantity=quantity,
                            pnl=0.0,
                            decision={
                                "decision": DecisionType.ENTER_LONG.value,
                                "reason_codes": list(getattr(signal, "reasons", [])),
                                "trade_date": bar.trade_date.isoformat(),
                                "cost_breakdown": trade_cost.cost_breakdown,
                            },
                            total_cost=trade_cost.total_cost,
                        )
                    )

            exposure = quantity * bar.close
            nav = cash + exposure
            heat = exposure / nav if nav > 0 else 0.0
            nav_series.append(nav)
            heat_series.append(heat)
            if previous_nav > 0:
                return_series.append((nav / previous_nav) - 1.0)
            previous_nav = nav
            daily_states.append(
                BacktestDailyState(
                    trade_date=bar.trade_date,
                    cash=round(cash, 3),
                    position_qty=quantity,
                    close_price=bar.close,
                    nav=round(nav, 3),
                    regime_label=str(getattr(regime, "label", "UNKNOWN")),
                    signal_state=str(getattr(signal, "state", "NONE")),
                    portfolio_heat=round(heat, 6),
                    exposure=round(exposure, 3),
                )
            )

        if quantity > 0 and bars:
            final_bar = bars[-1]
            trade_cost = self.cost_model.apply(final_bar.close, quantity, "sell", adv_turnover=max(final_bar.turnover, 1.0))
            cash += quantity * trade_cost.effective_price
            self._close_latest_trade(trades, final_bar.trade_date, trade_cost.effective_price, "FINAL_MARK_TO_MARKET", trade_cost.total_cost)
            final_nav = cash
            nav_series[-1] = final_nav
            heat_series[-1] = 0.0
            daily_states[-1].cash = round(cash, 3)
            daily_states[-1].position_qty = 0
            daily_states[-1].nav = round(final_nav, 3)
            daily_states[-1].portfolio_heat = 0.0
            daily_states[-1].exposure = 0.0

        summary = BacktestSummary(
            run_id=f"research-{dataset.symbol.lower()}-{dataset.date_range.start_date.isoformat()}",
            symbol=dataset.symbol,
            metrics=self._build_metrics(nav_series, return_series, trades, heat_series),
            assumptions=asdict(self.assumptions),
        )
        return BacktestResult(
            summary=summary,
            trades=trades,
            daily_states=daily_states,
            signals=signal_rows,
            dataset_report=self._dataset_report_dict(dataset.dataset_report),
        )

    def _close_latest_trade(self, trades: list[BacktestTrade], exit_date: date, exit_price: float, exit_reason: str, total_cost: float) -> None:
        for trade in reversed(trades):
            if trade.exit_date is None:
                trade.exit_date = exit_date
                trade.exit_price = exit_price
                trade.holding_period_days = max((exit_date - trade.entry_date).days, 0)
                trade.gross_pnl = round((exit_price - trade.entry_price) * trade.quantity, 3)
                trade.total_cost = round(trade.total_cost + total_cost, 3)
                trade.pnl = round(trade.gross_pnl - trade.total_cost, 3)
                trade.decision = {**trade.decision, "exit_reason": exit_reason, "exit_policy": exit_reason}
                break

    def _build_metrics(self, nav_series: list[float], return_series: list[float], trades: list[BacktestTrade], heat_series: list[float]) -> dict[str, float]:
        if not nav_series:
            return {"cagr": 0.0, "sharpe": 0.0, "sortino": 0.0, "max_drawdown": 0.0, "turnover": 0.0}
        years = max(len(nav_series) / 252.0, 1 / 252.0)
        cagr = ((nav_series[-1] / self.assumptions.initial_cash) ** (1 / years) - 1) if self.assumptions.initial_cash > 0 else 0.0
        avg_ret = sum(return_series) / len(return_series) if return_series else 0.0
        variance = sum((value - avg_ret) ** 2 for value in return_series) / len(return_series) if return_series else 0.0
        std_dev = sqrt(variance) if variance > 0 else 0.0
        downside = [value for value in return_series if value < 0]
        downside_var = sum(value**2 for value in downside) / len(downside) if downside else 0.0
        downside_dev = sqrt(downside_var) if downside_var > 0 else 0.0
        peak = nav_series[0]
        max_drawdown = 0.0
        drawdown_duration = 0
        current_duration = 0
        for nav in nav_series:
            peak = max(peak, nav)
            drawdown = (nav / peak) - 1.0 if peak else 0.0
            if drawdown < 0:
                current_duration += 1
            else:
                current_duration = 0
            drawdown_duration = max(drawdown_duration, current_duration)
            max_drawdown = min(max_drawdown, drawdown)
        wins = [trade for trade in trades if trade.pnl > 0]
        losses = [trade for trade in trades if trade.pnl < 0]
        avg_win = sum(trade.pnl for trade in wins) / len(wins) if wins else 0.0
        avg_loss = abs(sum(trade.pnl for trade in losses) / len(losses)) if losses else 0.0
        gross_profit = sum(trade.pnl for trade in wins)
        gross_loss = abs(sum(trade.pnl for trade in losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else gross_profit
        calmar = cagr / abs(max_drawdown) if max_drawdown < 0 else 0.0
        gross_profit_abs = sum(trade.gross_pnl for trade in trades if trade.gross_pnl > 0)
        gross_loss_abs = abs(sum(trade.gross_pnl for trade in trades if trade.gross_pnl < 0))
        gross_profit_factor = gross_profit_abs / gross_loss_abs if gross_loss_abs > 0 else gross_profit_abs
        gross_win_trades = [trade for trade in trades if trade.gross_pnl > 0]
        gross_loss_trades = [trade for trade in trades if trade.gross_pnl < 0]
        gross_payoff = (
            (sum(trade.gross_pnl for trade in gross_win_trades) / len(gross_win_trades))
            / abs(sum(trade.gross_pnl for trade in gross_loss_trades) / len(gross_loss_trades))
        ) if gross_win_trades and gross_loss_trades else 0.0
        holding_periods = sorted(trade.holding_period_days for trade in trades)
        median_holding = holding_periods[len(holding_periods) // 2] if holding_periods else 0.0
        p75_holding = holding_periods[int(len(holding_periods) * 0.75)] if holding_periods else 0.0
        short_hold_pct = sum(1 for trade in trades if trade.holding_period_days < 5) / len(trades) if trades else 0.0
        long_hold_profit = sum(trade.pnl for trade in trades if trade.holding_period_days >= 15 and trade.pnl > 0)
        positive_profit = sum(trade.pnl for trade in trades if trade.pnl > 0)
        sharpe = (avg_ret / std_dev * sqrt(252)) if std_dev > 0 else 0.0
        sortino = (avg_ret / downside_dev * sqrt(252)) if downside_dev > 0 else 0.0
        return {
            "cagr": round(cagr, 6),
            "sharpe": round(sharpe, 6),
            "sortino": round(sortino, 6),
            "max_drawdown": round(abs(max_drawdown), 6),
            "turnover": round(float(len(trades)), 6),
            "calmar": round(calmar, 6),
            "win_rate": round(len(wins) / len(trades), 6) if trades else 0.0,
            "payoff_ratio": round(avg_win / avg_loss, 6) if avg_loss > 0 else 0.0,
            "drawdown_duration_days": float(drawdown_duration),
            "profit_factor": round(profit_factor, 6) if gross_loss > 0 else round(profit_factor, 6),
            "avg_holding_period_days": round(sum(trade.holding_period_days for trade in trades) / len(trades), 6) if trades else 0.0,
            "portfolio_heat_max": round(max(heat_series) if heat_series else 0.0, 6),
            "gross_cagr_proxy": round(sum(trade.gross_pnl for trade in trades) / self.assumptions.initial_cash, 6) if trades else 0.0,
            "gross_sharpe_proxy": round(sharpe + ((sum(trade.total_cost for trade in trades) / self.assumptions.initial_cash) * 10), 6),
            "gross_sortino_proxy": round(sortino + ((sum(trade.total_cost for trade in trades) / self.assumptions.initial_cash) * 10), 6),
            "gross_profit_factor": round(gross_profit_factor, 6) if gross_loss_abs > 0 else round(gross_profit_factor, 6),
            "gross_payoff_ratio": round(gross_payoff, 6),
            "median_holding_period_days": float(median_holding),
            "p75_holding_period_days": float(p75_holding),
            "trades_under_5d_pct": round(short_hold_pct, 6),
            "profit_from_15d_plus_pct": round(long_hold_profit / positive_profit, 6) if positive_profit > 0 else 0.0,
        }

    def _dataset_report_dict(self, report) -> dict:
        return {
            "symbol": report.symbol,
            "first_available_date": report.first_available_date.isoformat() if report.first_available_date else None,
            "last_available_date": report.last_available_date.isoformat() if report.last_available_date else None,
            "missing_ranges": [{"start": start.isoformat(), "end": end.isoformat()} for start, end in report.missing_ranges],
            "unavailable_factor_families": list(report.unavailable_factor_families),
            "assumptions_applied": list(report.assumptions_applied),
            "degraded_fields": list(report.degraded_fields),
        }

    def _indicator_value(self, indicator, name: str, default: float) -> float:
        if indicator is None:
            return default
        return float(indicator.values.get(name, default))

    def _can_enter(self, screening, signal) -> bool:
        return bool(screening and screening.investable and signal and str(signal.state) in {"ENTER", "ENTER_PARTIAL"})

    def _signal_payload(self, dataset, bar, indicator, regime, screening, signal, cash, quantity, trailing_stop) -> dict:
        return {
            "symbol": dataset.symbol,
            "trade_date": bar.trade_date.isoformat(),
            "regime": {
                "label": getattr(getattr(regime, "label", None), "value", None),
                "confidence": getattr(regime, "confidence", 0.0),
                "factors": getattr(regime, "factors", {}),
                "degraded_factors": getattr(regime, "degraded_factors", []),
            },
            "screening": {
                "investable": getattr(screening, "investable", False),
                "passed_checks": getattr(screening, "passed_checks", []),
                "failed_checks": getattr(screening, "failed_checks", []),
                "risk_flags": getattr(screening, "risk_flags", []),
                "score": getattr(screening, "score", 0.0),
                "degraded": getattr(screening, "degraded", True),
            },
            "scores": {
                **(indicator.values if indicator else {}),
                "composite_score": getattr(signal, "composite_score", 0.0),
                "threshold": getattr(signal, "threshold", 0.0),
                "module_scores": getattr(signal, "module_scores", {}),
            },
            "market_data": {
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "turnover": bar.turnover,
                "delivery_pct": bar.delivery_pct,
            },
            "fundamentals": {"latest_snapshot": asdict(getattr(getattr(dataset, "screener_history", None), "latest_snapshot")) if getattr(getattr(dataset, "screener_history", None), "latest_snapshot", None) else {}},
            "portfolio_context": {"cash": round(cash, 3), "position_qty": quantity},
            "risk_plan": {"trailing_stop": round(trailing_stop, 3) if trailing_stop else None},
            "execution_plan": {
                "mode": "backtest",
                "next_session_execution": True,
                "slippage_bps": self.assumptions.slippage_bps,
                "fee_bps": self.assumptions.fee_bps,
            },
            "reason_codes": list(getattr(signal, "reasons", [])),
            "human_reason": self._human_reason(screening, signal),
        }

    def _human_reason(self, screening, signal) -> str:
        if screening and screening.investable and signal and str(signal.state) in {"ENTER", "ENTER_PARTIAL", "ADD_PARTIAL"}:
            return "Entry candidate passed the daily investability gate and cleared the composite score threshold."
        if screening and not screening.investable:
            return "Candidate was rejected because one or more daily screening gates failed."
        return "No actionable entry was generated for this session."


class CandidateResearchEngine:
    def __init__(
        self,
        assumptions: BacktestExecutionAssumptions,
        hal_rejection_profile: RejectionProfile | None = None,
        portfolio_rejection_profile: RejectionProfile | None = None,
    ) -> None:
        self.assumptions = assumptions
        self.hal_rejection_profile = hal_rejection_profile or assumptions.to_rejection_profile()
        self.portfolio_rejection_profile = portfolio_rejection_profile or assumptions.to_rejection_profile()

    def run_candidates(self, datasets, indicators, regimes, screenings, signal_candidates, symbol_profiles: dict[str, dict] | None = None) -> BacktestResult:
        requested_start_date = min(dataset.date_range.start_date for dataset in datasets.values())
        effective_start_date = max(
            min(bar.trade_date for bar in dataset.price_bars)
            for dataset in datasets.values()
            if dataset.price_bars
        )
        candidate_evaluations: dict[str, CandidateEvaluation] = {}
        best_result: BacktestResult | None = None
        winning_name: str | None = None
        symbol_profiles = symbol_profiles or {}

        for candidate_name, candidate_signals in signal_candidates.items():
            filtered = self._filter_inputs_by_start_date(datasets, indicators, regimes, screenings, candidate_signals, effective_start_date)
            result = self._run_portfolio(
                datasets=filtered["datasets"],
                signal_map_by_symbol=filtered["signals"],
                symbol_profiles=symbol_profiles,
            )
            window_metrics = self._window_metrics(filtered["datasets"], result)
            evaluation = self._evaluate_candidate(
                candidate_name,
                result.summary.metrics,
                window_metrics,
                effective_start_date,
                result.dataset_report.get("symbol_recommendations", {}),
                single_symbol=len(datasets) == 1,
            )
            candidate_evaluations[candidate_name] = evaluation
            if evaluation.status == CandidateStatus.ACCEPTED:
                if best_result is None or self._candidate_rank(evaluation) > self._candidate_rank(candidate_evaluations[winning_name]):  # type: ignore[index]
                    best_result = result
                    winning_name = candidate_name

        if best_result is None:
            winning_name = next(iter(candidate_evaluations.keys()))
            filtered = self._filter_inputs_by_start_date(datasets, indicators, regimes, screenings, signal_candidates[winning_name], effective_start_date)
            best_result = self._run_portfolio(
                datasets=filtered["datasets"],
                signal_map_by_symbol=filtered["signals"],
                symbol_profiles=symbol_profiles,
            )

        metric_leaders = self._metric_leaders(candidate_evaluations)
        filtered_adaptive_inputs = self._filter_all_candidate_inputs_by_start_date(
            datasets,
            signal_candidates,
            effective_start_date,
        )
        if len(datasets) == 1:
            only_symbol = next(iter(datasets.keys()))
            best_result = self._run_adaptive_single_symbol(
                dataset=filtered_adaptive_inputs["datasets"][only_symbol],
                candidate_signal_map={
                    name: symbol_signal_map[only_symbol]
                    for name, symbol_signal_map in filtered_adaptive_inputs["signals"].items()
                },
                candidate_evaluations=candidate_evaluations,
                symbol_profile=symbol_profiles.get(only_symbol, {}),
            )
        else:
            best_result = self._run_adaptive_portfolio(
                datasets=filtered_adaptive_inputs["datasets"],
                candidate_signal_maps=filtered_adaptive_inputs["signals"],
                candidate_evaluations=candidate_evaluations,
                symbol_profiles=symbol_profiles,
            )
        best_result.candidate_results = {
            name: {
                "status": evaluation.status.value,
                "rejection_reasons": list(evaluation.rejection_reasons),
                "enabled_modules": list(evaluation.enabled_modules),
                "disabled_modules": list(evaluation.disabled_modules),
                "effective_start_date": evaluation.effective_start_date.isoformat() if evaluation.effective_start_date else None,
                "hal_research_status": evaluation.hal_research_status,
                "portfolio_readiness_status": evaluation.portfolio_readiness_status,
                "hal_single_symbol_binding_blocker": evaluation.hal_single_symbol_binding_blocker,
                "portfolio_ready_binding_blocker": evaluation.portfolio_ready_binding_blocker,
                "oos_summary": evaluation.oos_summary,
                "is_summary": evaluation.is_summary,
                "metrics": evaluation.metrics,
                "symbol_recommendations": evaluation.symbol_recommendations,
                "candidate_assessment": {
                    "is_fallback_winner": name == winning_name,
                    "is_best_gross_edge_candidate": name == metric_leaders["best_gross_edge_candidate"],
                    "is_best_net_edge_candidate": name == metric_leaders["best_net_edge_candidate"],
                    "is_best_hold_quality_candidate": name == metric_leaders["best_hold_quality_candidate"],
                    "is_lowest_drawdown_duration_candidate": name == metric_leaders["lowest_drawdown_duration_candidate"],
                    "is_most_promising_candidate": name == metric_leaders["most_promising_candidate"],
                },
                "window_metrics": [
                    {
                        "window_label": window.window_label,
                        "in_sample_metrics": window.in_sample_metrics,
                        "out_of_sample_metrics": window.out_of_sample_metrics,
                    }
                    for window in evaluation.window_metrics
                ],
            }
            for name, evaluation in candidate_evaluations.items()
        }
        winning_eval = candidate_evaluations[winning_name]
        if len(datasets) == 1:
            only_symbol = next(iter(datasets.keys()))
            best_result.summary.run_id = f"research-{only_symbol.lower()}-{requested_start_date.isoformat()}"
            best_result.summary.symbol = only_symbol
        else:
            best_result.summary.run_id = f"{best_result.summary.run_id}-multi"
        promising_eval = candidate_evaluations[metric_leaders["most_promising_candidate"]] if metric_leaders["most_promising_candidate"] else winning_eval
        binding_blocker = self._binding_blocker(promising_eval) if metric_leaders["most_promising_candidate"] else "none"
        hal_tradable_under_any_candidate = any(
            evaluation.hal_research_status == "RESEARCH_PROMISING"
            and any(payload.get("recommendation") != "exclude" for payload in evaluation.symbol_recommendations.values())
            for evaluation in candidate_evaluations.values()
        )
        best_result.summary.metrics = {
            **best_result.summary.metrics,
            "winning_candidate": winning_name,
            "winning_candidate_status": winning_eval.status.value,
            "behavior_style": "owner_style_holding" if best_result.summary.metrics.get("avg_holding_period_days", 0.0) >= self.assumptions.min_avg_holding_period_days else "short_horizon_churn",
            "current_fallback_winner": winning_name,
            "strongest_raw_candidate": metric_leaders["best_net_edge_candidate"],
            "best_gross_edge_candidate": metric_leaders["best_gross_edge_candidate"],
            "best_net_edge_candidate": metric_leaders["best_net_edge_candidate"],
            "best_hold_quality_candidate": metric_leaders["best_hold_quality_candidate"],
            "lowest_drawdown_duration_candidate": metric_leaders["lowest_drawdown_duration_candidate"],
            "most_promising_candidate": metric_leaders["most_promising_candidate"],
            "hal_tradable_under_any_candidate": hal_tradable_under_any_candidate,
            "closest_to_viability_metric": binding_blocker,
            "active_selector_model": "adaptive_switch",
            "current_selected_hal_strategy": best_result.dataset_report.get("current_selected_hal_strategy", "n/a"),
            "current_exit_policy_behavior": best_result.dataset_report.get("current_exit_policy_behavior", "n/a"),
            "hal_research_status": promising_eval.hal_research_status,
            "portfolio_readiness_status": promising_eval.portfolio_readiness_status,
            "hal_single_symbol_binding_blocker": promising_eval.hal_single_symbol_binding_blocker,
            "portfolio_ready_binding_blocker": promising_eval.portfolio_ready_binding_blocker,
            "module_decisions": best_result.dataset_report.get("module_decisions", {}),
            "selected_strategy_mix": best_result.dataset_report.get("selected_strategy_mix", {}),
            "best_aligned_symbols": [
                symbol
                for symbol, payload in winning_eval.symbol_recommendations.items()
                if payload.get("recommendation") in {"retain", "accumulate-only", "breakout-only"}
            ],
        }
        best_result.period_summaries = self._build_period_summaries(best_result)
        entry_blocker_counts = Counter()
        for row in best_result.signals:
            entry_blocker_counts.update(row.get("screening_blockers", []))
            entry_blocker_counts.update(row.get("entry_blockers", []))
        best_result.dataset_report = {
            "symbols": list(datasets.keys()),
            "requested_start_date": requested_start_date.isoformat(),
            "effective_portfolio_start_date": effective_start_date.isoformat(),
            "use_common_start_date": True,
            "assumptions_applied": ["portfolio_heat_cap", "config_driven_costs", "next_session_execution", "common_start_date", "staged_entries", "partial_exits"],
            "symbol_recommendations": best_result.dataset_report.get("symbol_recommendations", winning_eval.symbol_recommendations),
            "average_tranches_per_position": best_result.dataset_report.get("average_tranches_per_position", 0.0),
            "candidate_metric_leaders": metric_leaders,
            "selected_strategy_mix": best_result.dataset_report.get("selected_strategy_mix", {}),
            "current_selected_hal_strategy": best_result.dataset_report.get("current_selected_hal_strategy", "n/a"),
            "current_exit_policy_behavior": best_result.dataset_report.get("current_exit_policy_behavior", "n/a"),
            "concurrent_usage": best_result.dataset_report.get("concurrent_usage", {}),
            "deployment_summary": best_result.dataset_report.get("deployment_summary", best_result.dataset_report.get("concurrent_usage", {})),
            "slot_block_reason_counts": best_result.dataset_report.get("slot_block_reason_counts", {}),
            "entry_blocker_counts": dict(entry_blocker_counts),
            "module_decisions": best_result.dataset_report.get("module_decisions", {}),
            "period_summaries": best_result.period_summaries,
            "screening_summary": best_result.dataset_report.get("screening_summary", {}),
            "symbol_health_diagnostics": best_result.dataset_report.get("symbol_recommendations", winning_eval.symbol_recommendations),
        }
        return best_result

    def _filter_inputs_by_start_date(self, datasets, indicators, regimes, screenings, signals, start_date: date) -> dict:
        filtered_datasets = {}
        filtered_signals = {}
        for symbol, dataset in datasets.items():
            filtered_datasets[symbol] = ResearchDataset(
                symbol=dataset.symbol,
                benchmark_symbol=dataset.benchmark_symbol,
                date_range=dataset.date_range,
                price_bars=[bar for bar in dataset.price_bars if bar.trade_date >= start_date],
                benchmark_bars=[bar for bar in dataset.benchmark_bars if bar.trade_date >= start_date],
                vix_history={key: value for key, value in dataset.vix_history.items() if key >= start_date},
                corporate_actions={key: value for key, value in dataset.corporate_actions.items() if key >= start_date},
                event_calendar={key: value for key, value in dataset.event_calendar.items() if key >= start_date},
                screener_history=dataset.screener_history,
                dataset_report=dataset.dataset_report,
            )
            filtered_signals[symbol] = [signal for signal in signals[symbol] if signal.trade_date >= start_date]
        return {"datasets": filtered_datasets, "signals": filtered_signals}

    def _filter_all_candidate_inputs_by_start_date(self, datasets, signal_candidates, start_date: date) -> dict:
        filtered_datasets = {}
        for symbol, dataset in datasets.items():
            filtered_datasets[symbol] = ResearchDataset(
                symbol=dataset.symbol,
                benchmark_symbol=dataset.benchmark_symbol,
                date_range=dataset.date_range,
                price_bars=[bar for bar in dataset.price_bars if bar.trade_date >= start_date],
                benchmark_bars=[bar for bar in dataset.benchmark_bars if bar.trade_date >= start_date],
                vix_history={key: value for key, value in dataset.vix_history.items() if key >= start_date},
                corporate_actions={key: value for key, value in dataset.corporate_actions.items() if key >= start_date},
                event_calendar={key: value for key, value in dataset.event_calendar.items() if key >= start_date},
                screener_history=dataset.screener_history,
                dataset_report=dataset.dataset_report,
            )
        filtered_signals = {
            candidate_name: {
                symbol: [signal for signal in symbol_signals if signal.trade_date >= start_date]
                for symbol, symbol_signals in symbol_map.items()
            }
            for candidate_name, symbol_map in signal_candidates.items()
        }
        return {"datasets": filtered_datasets, "signals": filtered_signals}

    def _evaluate_candidate(
        self,
        candidate_name: str,
        metrics: dict[str, float],
        window_metrics: list[WindowMetrics],
        effective_start_date: date,
        symbol_recommendations: dict[str, dict],
        single_symbol: bool = False,
    ) -> CandidateEvaluation:
        portfolio_rejection_reasons = self._evaluate_against_profile(metrics, window_metrics, symbol_recommendations, self.portfolio_rejection_profile, single_symbol=False)
        hal_rejection_reasons = self._evaluate_against_profile(metrics, window_metrics, symbol_recommendations, self.hal_rejection_profile, single_symbol=True)
        rejection_reasons = hal_rejection_reasons if single_symbol else portfolio_rejection_reasons
        status = CandidateStatus.ACCEPTED
        oos_summary = self._combine_metric_map([window.out_of_sample_metrics for window in window_metrics])
        is_summary = self._combine_metric_map([window.in_sample_metrics for window in window_metrics])
        oos_sharpe = oos_summary.get("sharpe", 0.0)
        is_sharpe = is_summary.get("sharpe", 0.0)
        sharpe_drop_pct = ((is_sharpe - oos_sharpe) / abs(is_sharpe) * 100.0) if is_sharpe not in {0.0, -0.0} else 0.0
        oos_summary["sharpe_drop_pct"] = round(sharpe_drop_pct, 6)
        window_trade_counts = [window.out_of_sample_metrics.get("trade_count", 0.0) for window in window_metrics]
        window_signal_counts = [window.out_of_sample_metrics.get("signal_count", 0.0) for window in window_metrics]
        low_sample_windows = sum(1 for window in window_metrics if window.out_of_sample_metrics.get("low_sample_window", 0.0) >= 1.0)
        oos_summary["window_trade_counts"] = window_trade_counts
        oos_summary["window_signal_counts"] = window_signal_counts
        oos_summary["low_sample_windows"] = float(low_sample_windows)
        oos_summary["effective_validation_trade_count"] = float(sum(window_trade_counts))
        oos_summary["walk_forward_confidence"] = "low" if low_sample_windows > 0 or sum(window_trade_counts) < max(5, self.assumptions.min_trade_count) else "medium"
        if single_symbol and CandidateStatus.REJECTED_DRAWDOWN_DURATION.value in hal_rejection_reasons:
            hal_rejection_reasons = [reason for reason in hal_rejection_reasons if reason != CandidateStatus.REJECTED_DRAWDOWN_DURATION.value]
        if rejection_reasons:
            status = CandidateStatus(rejection_reasons[0])
        enabled_modules = ["trend", "pullback", "momentum_quality", "fundamental_quality", "liquidity_gate", "regime_gate", "staged_entries", "partial_exits"]
        disabled_modules = []
        if "event" in candidate_name:
            enabled_modules.append("event_drift")
        else:
            disabled_modules.append("event_drift")
        if "seasonality" in candidate_name:
            enabled_modules.append("seasonality")
        else:
            disabled_modules.append("seasonality")
        return CandidateEvaluation(
            name=candidate_name,
            status=status,
            rejection_reasons=rejection_reasons,
            enabled_modules=enabled_modules,
            disabled_modules=disabled_modules,
            effective_start_date=effective_start_date,
            oos_summary=oos_summary,
            is_summary=is_summary,
            metrics=metrics,
            window_metrics=window_metrics,
            symbol_recommendations=symbol_recommendations,
            hal_research_status="RESEARCH_PROMISING" if not hal_rejection_reasons else "RESEARCH_BLOCKED",
            portfolio_readiness_status="PORTFOLIO_READY" if not portfolio_rejection_reasons else "PORTFOLIO_BLOCKED",
            hal_single_symbol_binding_blocker=self._first_reason_to_blocker(hal_rejection_reasons, "accepted"),
            portfolio_ready_binding_blocker=self._first_reason_to_blocker(portfolio_rejection_reasons, "accepted"),
        )

    def _window_metrics(self, datasets, result: BacktestResult) -> list[WindowMetrics]:
        trade_dates = [state.trade_date for state in result.daily_states]
        years = sorted({trade_date.year for trade_date in trade_dates})
        windows: list[WindowMetrics] = []
        for year in years[1:]:
            train_end = date(year - 1, 12, 31)
            test_start = date(year, 1, 1)
            test_end = date(year, 12, 31)
            is_metrics = self._metrics_for_date_slice(result, None, train_end)
            oos_metrics = self._metrics_for_date_slice(result, test_start, test_end)
            windows.append(WindowMetrics(window_label=f"{year-1}->{year}", in_sample_metrics=is_metrics, out_of_sample_metrics=oos_metrics))
        if not windows:
            full_metrics = self._metrics_for_date_slice(result, None, None)
            windows.append(
                WindowMetrics(
                    window_label="full_sample",
                    in_sample_metrics=full_metrics,
                    out_of_sample_metrics=full_metrics,
                )
            )
        return windows

    def _metrics_for_date_slice(self, result: BacktestResult, start_date: date | None, end_date: date | None) -> dict[str, float]:
        states = [
            state
            for state in result.daily_states
            if (start_date is None or state.trade_date >= start_date) and (end_date is None or state.trade_date <= end_date)
        ]
        trades = [
            trade
            for trade in result.trades
            if trade.exit_date is not None
            and (start_date is None or trade.exit_date >= start_date)
            and (end_date is None or trade.exit_date <= end_date)
        ]
        signals = [
            row
            for row in result.signals
            if (start_date is None or date.fromisoformat(row["trade_date"]) >= start_date)
            and (end_date is None or date.fromisoformat(row["trade_date"]) <= end_date)
        ]
        if not states:
            return {
                "sharpe": 0.0,
                "cagr": 0.0,
                "turnover": 0.0,
                "avg_holding_period_days": 0.0,
                "trade_count": 0.0,
                "signal_count": 0.0,
                "low_sample_window": 1.0,
            }
        navs = [state.nav for state in states]
        heat_series = [state.portfolio_heat for state in states]
        returns = []
        for previous, current in zip(navs, navs[1:]):
            if previous > 0:
                returns.append((current / previous) - 1.0)
        metrics = WalkForwardBacktestEngine(self.assumptions)._build_metrics(navs, returns, trades, heat_series)
        metrics["trade_count"] = float(len(trades))
        metrics["signal_count"] = float(len(signals))
        metrics["low_sample_window"] = 1.0 if len(trades) < max(3, self.assumptions.min_trade_count // 2) else 0.0
        return metrics

    def _combine_metric_map(self, metric_maps: list[dict[str, float]]) -> dict[str, float]:
        if not metric_maps:
            return {}
        keys = {key for metric_map in metric_maps for key in metric_map.keys()}
        return {key: round(sum(metric_map.get(key, 0.0) for metric_map in metric_maps) / len(metric_maps), 6) for key in keys}

    def _candidate_rank(self, evaluation: CandidateEvaluation) -> tuple[float, float, float, float]:
        return (
            evaluation.oos_summary.get("sharpe", 0.0),
            -evaluation.metrics.get("max_drawdown", 1.0),
            evaluation.metrics.get("avg_holding_period_days", 0.0),
            evaluation.metrics.get("cagr", 0.0),
        )

    def _evaluate_against_profile(
        self,
        metrics: dict[str, float],
        window_metrics: list[WindowMetrics],
        symbol_recommendations: dict[str, dict],
        profile: RejectionProfile,
        single_symbol: bool,
    ) -> list[str]:
        rejection_reasons: list[str] = []
        if metrics.get("gross_cagr_proxy", 0.0) <= profile.min_cagr or metrics.get("gross_profit_factor", 0.0) <= profile.min_profit_factor or metrics.get("gross_sharpe_proxy", 0.0) <= profile.min_sharpe:
            rejection_reasons.append(CandidateStatus.REJECTED_NEGATIVE_EDGE.value)
        if metrics.get("max_drawdown", 0.0) > profile.max_drawdown:
            rejection_reasons.append(CandidateStatus.REJECTED_DRAWDOWN.value)
        if metrics.get("drawdown_duration_days", 0.0) > profile.max_drawdown_duration_days:
            rejection_reasons.append(CandidateStatus.REJECTED_DRAWDOWN_DURATION.value)
        if metrics.get("turnover", 0.0) > profile.max_turnover:
            rejection_reasons.append(CandidateStatus.REJECTED_TURNOVER.value)
        if metrics.get("avg_holding_period_days", 0.0) < profile.min_avg_holding_period_days:
            rejection_reasons.append(CandidateStatus.REJECTED_HOLDING_PERIOD.value)
        if metrics.get("portfolio_heat_max", 0.0) > profile.max_portfolio_heat:
            rejection_reasons.append(CandidateStatus.REJECTED_HEAT_BREACH.value)
        if metrics.get("turnover", 0.0) < profile.min_trade_count:
            rejection_reasons.append(CandidateStatus.REJECTED_TOO_FEW_TRADES.value)
        excluded_like = {"exclude", "ghost_no_signals", "data_problem"}
        if not single_symbol and len(symbol_recommendations) > 0 and sum(1 for payload in symbol_recommendations.values() if payload.get("recommendation") in excluded_like) >= max(1, len(symbol_recommendations) - 1):
            rejection_reasons.append(CandidateStatus.REJECTED_CONCENTRATION.value)
        oos_summary = self._combine_metric_map([window.out_of_sample_metrics for window in window_metrics])
        is_summary = self._combine_metric_map([window.in_sample_metrics for window in window_metrics])
        oos_sharpe = oos_summary.get("sharpe", 0.0)
        is_sharpe = is_summary.get("sharpe", 0.0)
        sharpe_drop_pct = ((is_sharpe - oos_sharpe) / abs(is_sharpe) * 100.0) if is_sharpe not in {0.0, -0.0} else 0.0
        if sharpe_drop_pct > profile.max_oos_sharpe_drop_pct:
            rejection_reasons.append(CandidateStatus.REJECTED_OOS_DECAY.value)
        return rejection_reasons

    def _first_reason_to_blocker(self, reasons: list[str], default: str) -> str:
        reason_map = {
            CandidateStatus.REJECTED_NEGATIVE_EDGE.value: "gross_edge",
            CandidateStatus.REJECTED_DRAWDOWN.value: "max_drawdown",
            CandidateStatus.REJECTED_DRAWDOWN_DURATION.value: "drawdown_duration_days",
            CandidateStatus.REJECTED_TURNOVER.value: "turnover",
            CandidateStatus.REJECTED_HOLDING_PERIOD.value: "avg_holding_period_days",
            CandidateStatus.REJECTED_OOS_DECAY.value: "oos_sharpe_drop_pct",
            CandidateStatus.REJECTED_TOO_FEW_TRADES.value: "trade_count_confidence",
            CandidateStatus.REJECTED_CONCENTRATION.value: "symbol_concentration",
            CandidateStatus.REJECTED_HEAT_BREACH.value: "portfolio_heat_max",
            CandidateStatus.REJECTED_SEASONALITY_FRAGILE.value: "seasonality_robustness",
        }
        for reason in reasons:
            if reason in reason_map:
                return reason_map[reason]
        return default

    def _metric_leaders(self, candidate_evaluations: dict[str, CandidateEvaluation]) -> dict[str, str | None]:
        if not candidate_evaluations:
            return {
                "best_gross_edge_candidate": None,
                "best_net_edge_candidate": None,
                "best_hold_quality_candidate": None,
                "lowest_drawdown_duration_candidate": None,
                "most_promising_candidate": None,
            }

        def gross_rank(item):
            _, evaluation = item
            return (
                evaluation.metrics.get("gross_profit_factor", 0.0),
                evaluation.metrics.get("gross_sharpe_proxy", 0.0),
                evaluation.metrics.get("gross_cagr_proxy", 0.0),
            )

        def net_rank(item):
            _, evaluation = item
            return (
                evaluation.metrics.get("profit_factor", 0.0),
                evaluation.metrics.get("sharpe", 0.0),
                evaluation.metrics.get("cagr", 0.0),
            )

        def hold_rank(item):
            _, evaluation = item
            return (
                evaluation.metrics.get("profit_from_15d_plus_pct", 0.0),
                evaluation.metrics.get("avg_holding_period_days", 0.0),
                -evaluation.metrics.get("trades_under_5d_pct", 1.0),
            )

        def drawdown_rank(item):
            _, evaluation = item
            return (
                -evaluation.metrics.get("drawdown_duration_days", float("inf")),
                -evaluation.metrics.get("max_drawdown", float("inf")),
            )

        def promise_rank(item):
            _, evaluation = item
            penalty = len(evaluation.rejection_reasons)
            blocker_penalty = 0 if CandidateStatus.REJECTED_DRAWDOWN_DURATION.value in evaluation.rejection_reasons else 1
            return (
                evaluation.metrics.get("profit_factor", 0.0),
                evaluation.metrics.get("sharpe", 0.0),
                evaluation.metrics.get("avg_holding_period_days", 0.0),
                -penalty,
                -blocker_penalty,
            )

        return {
            "best_gross_edge_candidate": max(candidate_evaluations.items(), key=gross_rank)[0],
            "best_net_edge_candidate": max(candidate_evaluations.items(), key=net_rank)[0],
            "best_hold_quality_candidate": max(candidate_evaluations.items(), key=hold_rank)[0],
            "lowest_drawdown_duration_candidate": max(candidate_evaluations.items(), key=drawdown_rank)[0],
            "most_promising_candidate": max(candidate_evaluations.items(), key=promise_rank)[0],
        }

    def _binding_blocker(self, evaluation: CandidateEvaluation) -> str:
        return self._first_reason_to_blocker(evaluation.rejection_reasons, "accepted")

    def _run_adaptive_single_symbol(
        self,
        dataset: ResearchDataset,
        candidate_signal_map: dict[str, list],
        candidate_evaluations: dict[str, CandidateEvaluation],
        symbol_profile: dict,
    ) -> BacktestResult:
        bars = sorted(dataset.price_bars, key=lambda item: item.trade_date)
        signal_lookup = {
            candidate: {signal.trade_date: signal for signal in signals}
            for candidate, signals in candidate_signal_map.items()
        }
        cost_model = CostModel(self.assumptions)
        symbol = dataset.symbol
        cash = self.assumptions.initial_cash
        trades: list[BacktestTrade] = []
        daily_states: list[BacktestDailyState] = []
        signal_rows: list[dict] = []
        nav_series: list[float] = []
        heat_series: list[float] = []
        return_series: list[float] = []
        previous_nav = cash
        position: dict | None = None

        for idx, bar in enumerate(bars):
            next_bar = bars[idx + 1] if idx + 1 < len(bars) else None
            candidate_signals = {
                name: lookup.get(bar.trade_date)
                for name, lookup in signal_lookup.items()
                if lookup.get(bar.trade_date) is not None
            }
            selector = self._select_adaptive_strategy(candidate_signals, candidate_evaluations, position, bar)
            selected_signal = selector["signal"]
            selected_strategy = selector["selected_strategy"]
            profit_state = self._profit_state(position, bar.close)
            position_stage = self._position_stage(position)
            regime_deterioration_level = self._regime_deterioration_level(selected_signal)

            exit_policy = "NONE"
            exit_severity = "none"
            if position is not None:
                position["highest_close"] = max(position["highest_close"], bar.close)
                current_atr = float(getattr(selected_signal, "screening_details", {}).get("atr_14", max(bar.close * 0.02, 1.0)))
                position["trailing_stop"] = max(position["trailing_stop"], position["highest_close"] - current_atr * position.get("atr_stop_multiplier", self.assumptions.atr_stop_multiplier))
                exit_policy, exit_severity = self._adaptive_exit_policy(position, bar, selected_signal, profit_state, regime_deterioration_level)
                if exit_policy == "EXIT_ON_HARD_RISK" and next_bar is not None:
                    trade_cost = cost_model.apply(next_bar.open, position["quantity"], "sell", adv_turnover=max(bar.turnover, 1.0))
                    cash += position["quantity"] * trade_cost.effective_price
                    self._close_open_tranches(
                        trades,
                        list(position["open_trade_indexes"]),
                        next_bar.trade_date,
                        trade_cost,
                        "EXIT_FULL",
                        exit_policy,
                    )
                    position = None
                elif exit_policy in {"REDUCE_ON_EXTENSION", "REDUCE_ON_REGIME_SOFTENING"} and position is not None and len(position["open_trade_indexes"]) > 1 and next_bar is not None:
                    trade_index = position["open_trade_indexes"].pop()
                    reduce_qty = trades[trade_index].quantity
                    trade_cost = cost_model.apply(next_bar.open, reduce_qty, "sell", adv_turnover=max(bar.turnover, 1.0))
                    cash += reduce_qty * trade_cost.effective_price
                    self._close_open_tranches(trades, [trade_index], next_bar.trade_date, trade_cost, "REDUCE_PARTIAL", exit_policy)
                    position["quantity"] -= reduce_qty
                elif exit_policy in {"EXIT_ON_INVALIDATION", "EXIT_ON_TIME_DECAY"} and next_bar is not None:
                    trade_cost = cost_model.apply(next_bar.open, position["quantity"], "sell", adv_turnover=max(bar.turnover, 1.0))
                    cash += position["quantity"] * trade_cost.effective_price
                    self._close_open_tranches(
                        trades,
                        list(position["open_trade_indexes"]),
                        next_bar.trade_date,
                        trade_cost,
                        "EXIT_FULL",
                        exit_policy,
                    )
                    position = None

            if position is not None and selected_signal and str(selected_signal.state) == "ADD_PARTIAL" and next_bar is not None and self._can_add_position(position, selected_signal, bar):
                quantity = self._target_quantity(cash, next_bar.open, tranche_fraction=0.20)
                if quantity > 0:
                    trade_cost = cost_model.apply(next_bar.open, quantity, "buy", adv_turnover=max(bar.turnover, 1.0))
                    total_cash_need = quantity * trade_cost.effective_price
                    if total_cash_need <= cash:
                        cash -= total_cash_need
                        trades.append(
                            BacktestTrade(
                                symbol=symbol,
                                entry_date=next_bar.trade_date,
                                exit_date=None,
                                entry_price=trade_cost.effective_price,
                                exit_price=None,
                                quantity=quantity,
                                pnl=0.0,
                                decision={
                                    "decision": "ADD_PARTIAL",
                                    "trade_date": bar.trade_date.isoformat(),
                            "reason_codes": list(selected_signal.reasons),
                            "cost_breakdown": trade_cost.cost_breakdown,
                            "tranche_number": len(position["open_trade_indexes"]) + 1,
                            "selected_strategy": selected_strategy,
                            "entry_band": getattr(selected_signal, "entry_band", "reject"),
                        },
                                total_cost=trade_cost.total_cost,
                            )
                        )
                        position["open_trade_indexes"].append(len(trades) - 1)
                        position["quantity"] += quantity
                        position["avg_entry_price"] = self._avg_entry_price(trades, position["open_trade_indexes"])

            if position is None and selected_signal and str(selected_signal.state) == "ENTER_PARTIAL" and next_bar is not None:
                quantity = self._target_quantity(cash, next_bar.open, tranche_fraction=0.30)
                if quantity > 0:
                    trade_cost = cost_model.apply(next_bar.open, quantity, "buy", adv_turnover=max(bar.turnover, 1.0))
                    total_cash_need = quantity * trade_cost.effective_price
                    if total_cash_need <= cash:
                        cash -= total_cash_need
                        trades.append(
                            BacktestTrade(
                                symbol=symbol,
                                entry_date=next_bar.trade_date,
                                exit_date=None,
                                entry_price=trade_cost.effective_price,
                                exit_price=None,
                                quantity=quantity,
                                pnl=0.0,
                                decision={
                                    "decision": "ENTER_PARTIAL",
                                    "trade_date": bar.trade_date.isoformat(),
                            "reason_codes": list(selected_signal.reasons),
                            "cost_breakdown": trade_cost.cost_breakdown,
                            "tranche_number": 1,
                            "selected_strategy": selected_strategy,
                            "entry_band": getattr(selected_signal, "entry_band", "reject"),
                        },
                                total_cost=trade_cost.total_cost,
                            )
                        )
                        position = {
                            "quantity": quantity,
                            "entry_date": next_bar.trade_date,
                            "entry_price": trade_cost.effective_price,
                            "avg_entry_price": trade_cost.effective_price,
                            "highest_close": next_bar.close,
                            "trailing_stop": trade_cost.effective_price - float(getattr(selected_signal, "screening_details", {}).get("atr_14", max(next_bar.close * 0.02, 1.0))) * self._symbol_atr_multiplier(symbol_profile),
                            "atr_stop_multiplier": self._symbol_atr_multiplier(symbol_profile),
                            "open_trade_indexes": [len(trades) - 1],
                        }

            exposure = position["quantity"] * bar.close if position is not None else 0.0
            nav = cash + exposure
            heat = exposure / nav if nav > 0 else 0.0
            nav_series.append(nav)
            heat_series.append(heat)
            if previous_nav > 0:
                return_series.append((nav / previous_nav) - 1.0)
            previous_nav = nav
            signal_rows.append(
                {
                    "symbol": symbol,
                    "trade_date": bar.trade_date.isoformat(),
                    "selected_strategy": selected_strategy,
                    "selected_signal_state": selector.get("selected_signal_state", str(getattr(selected_signal, "state", "REJECT"))),
                    "selection_reason": selector["selection_reason"],
                    "selection_confidence": selector["selection_confidence"],
                    "selected_score_margin": selector.get("selected_score_margin", round(getattr(selected_signal, "score_margin", 0.0), 6)),
                    "candidate_actionability_rank": selector.get("candidate_actionability_rank", []),
                    "signal_state": str(getattr(selected_signal, "state", "REJECT")),
                    "candidate_reason_codes": list(getattr(selected_signal, "reasons", [])),
                    "composite_score": getattr(selected_signal, "composite_score", 0.0),
                    "screening_pass": getattr(selected_signal, "screening_pass", False),
                    "screening_blockers": list(getattr(selected_signal, "screening_blockers", [])),
                    "soft_blockers": list(getattr(selected_signal, "soft_blockers", [])),
                    "entry_band": getattr(selected_signal, "entry_band", "reject"),
                    "entry_blockers": list(getattr(selected_signal, "entry_blockers", [])),
                    "exit_policy": exit_policy,
                    "exit_severity": exit_severity,
                    "position_stage": position_stage,
                    "profit_state": profit_state,
                    "regime_deterioration_level": regime_deterioration_level,
                }
            )
            daily_states.append(
                BacktestDailyState(
                    trade_date=bar.trade_date,
                    cash=round(cash, 3),
                    position_qty=position["quantity"] if position is not None else 0,
                    close_price=round(bar.close, 3),
                    nav=round(nav, 3),
                    regime_label="HAL_ADAPTIVE",
                    signal_state=str(getattr(selected_signal, "state", "REJECT")),
                    portfolio_heat=round(heat, 6),
                    exposure=round(exposure, 3),
                    selected_strategy=selected_strategy,
                    exit_policy=exit_policy,
                    exit_severity=exit_severity,
                    position_stage=position_stage,
                    profit_state=profit_state,
                    regime_deterioration_level=regime_deterioration_level,
                )
            )

        if position is not None and bars:
            final_bar = bars[-1]
            trade_cost = cost_model.apply(final_bar.close, position["quantity"], "sell", adv_turnover=max(final_bar.turnover, 1.0))
            cash += position["quantity"] * trade_cost.effective_price
            self._close_open_tranches(
                trades,
                list(position["open_trade_indexes"]),
                final_bar.trade_date,
                trade_cost,
                "EXIT_FULL",
                "FINAL_MARK_TO_MARKET",
            )
            nav_series[-1] = cash
            heat_series[-1] = 0.0
            daily_states[-1].cash = round(cash, 3)
            daily_states[-1].position_qty = 0
            daily_states[-1].nav = round(cash, 3)
            daily_states[-1].portfolio_heat = 0.0
            daily_states[-1].exposure = 0.0

        symbol_recommendations = self._symbol_recommendations(trades, {symbol: symbol_profile})
        selected_counts: dict[str, int] = {}
        for row in signal_rows:
            selected_counts[row["selected_strategy"]] = selected_counts.get(row["selected_strategy"], 0) + 1
        summary = BacktestSummary(
            run_id=f"research-{symbol.lower()}-{dataset.date_range.start_date.isoformat()}",
            symbol=symbol,
            metrics=WalkForwardBacktestEngine(self.assumptions)._build_metrics(nav_series, return_series, trades, heat_series),
            assumptions=asdict(self.assumptions),
        )
        return BacktestResult(
            summary=summary,
            trades=trades,
            daily_states=daily_states,
            signals=signal_rows,
            dataset_report={
                "symbols": [symbol],
                "assumptions_applied": ["adaptive_switch", "staged_entries", "partial_exits", "hal_single_symbol_gates"],
                "symbol_recommendations": symbol_recommendations,
                "average_tranches_per_position": round(sum(item["avg_tranches"] for item in symbol_recommendations.values()) / len(symbol_recommendations), 3) if symbol_recommendations else 0.0,
                "current_selected_hal_strategy": max(selected_counts, key=selected_counts.get) if selected_counts else "n/a",
                "current_exit_policy_behavior": self._dominant_exit_policy(signal_rows),
                "selected_strategy_mix": self._normalize_counter(selected_counts),
                "concurrent_usage": self._concurrent_usage_metrics(daily_states),
                "deployment_summary": self._concurrent_usage_metrics(daily_states),
                "slot_block_reason_counts": {},
                "entry_blocker_counts": dict(Counter(blocker for row in signal_rows for blocker in row.get("entry_blockers", []))),
                "screening_summary": {
                    symbol: {
                        "screening_pass_rate": payload.get("screening_pass_rate", 0.0),
                        "actionable_signal_rate": payload.get("actionable_signal_rate", 0.0),
                        "trade_conversion_rate": payload.get("trade_conversion_rate", 0.0),
                    }
                    for symbol, payload in symbol_recommendations.items()
                },
                "symbol_health_diagnostics": symbol_recommendations,
                "module_decisions": {
                    "event_drift": {
                        "enabled": any(row["selected_strategy"] == "franchise_event_drift" for row in signal_rows),
                        "reason": "bounded event window" if any(row["selected_strategy"] == "franchise_event_drift" for row in signal_rows) else "event overlay not selected by adaptive switch",
                    },
                    "seasonality": {
                        "enabled": any(row["selected_strategy"] == "franchise_seasonality_enabled" for row in signal_rows),
                        "reason": "validated selector preference" if any(row["selected_strategy"] == "franchise_seasonality_enabled" for row in signal_rows) else "not validated",
                    },
                },
            },
        )

    def _normalize_counter(self, counts: Counter) -> dict[str, float]:
        total = sum(counts.values())
        if total <= 0:
            return {}
        return {name: round(value / total, 6) for name, value in sorted(counts.items())}

    def _concurrent_usage_metrics(self, daily_states: list[BacktestDailyState]) -> dict[str, float]:
        if not daily_states:
            return {
                "avg_concurrent_positions": 0.0,
                "max_concurrent_positions_used": 0.0,
                "days_with_any_position_pct": 0.0,
                "days_with_2plus_positions_pct": 0.0,
                "days_with_3_positions_pct": 0.0,
                "cash_idle_pct": 0.0,
                "average_invested_capital_pct": 0.0,
            }
        position_counts = []
        idle_days = 0
        invested_capital = 0.0
        for state in daily_states:
            if isinstance(state.position_qty, dict):
                count = sum(1 for qty in state.position_qty.values() if qty > 0)
            else:
                count = 1 if state.position_qty > 0 else 0
            position_counts.append(count)
            if count == 0:
                idle_days += 1
            invested_capital += state.portfolio_heat
        total_days = len(position_counts)
        return {
            "avg_concurrent_positions": round(sum(position_counts) / total_days, 6),
            "max_concurrent_positions_used": float(max(position_counts) if position_counts else 0),
            "days_with_any_position_pct": round(sum(1 for count in position_counts if count >= 1) / total_days, 6),
            "days_with_2plus_positions_pct": round(sum(1 for count in position_counts if count >= 2) / total_days, 6),
            "days_with_3_positions_pct": round(sum(1 for count in position_counts if count >= 3) / total_days, 6),
            "cash_idle_pct": round(idle_days / total_days, 6),
            "average_invested_capital_pct": round(invested_capital / total_days, 6),
        }

    def _entry_band_priority(self, entry_band: str | None) -> int:
        priorities = {
            "high_conviction_entry": 3,
            "standard_entry": 2,
            "watchlist_hold": 1,
            "reject": 0,
            None: 0,
        }
        return priorities.get(entry_band, 0)

    def _signal_state_priority(self, signal_state: str | None) -> int:
        priorities = {
            "ENTER_PARTIAL": 4,
            "ADD_PARTIAL": 3,
            "HOLD": 2,
            "REDUCE_PARTIAL": 1,
            "EXIT_FULL": 1,
            "REJECT": 0,
            None: 0,
        }
        return priorities.get(signal_state, 0)

    def _symbol_atr_multiplier(self, symbol_profile: dict | None) -> float:
        strategy = (symbol_profile or {}).get("strategy", {})
        return float(strategy.get("atr_stop_multiplier", self.assumptions.atr_stop_multiplier))

    def _build_period_summaries(self, result: BacktestResult) -> dict[str, object]:
        if not result.daily_states:
            return {}

        def period_key(trade_date: date, level: str) -> str:
            if level == "weekly":
                iso_year, iso_week, _ = trade_date.isocalendar()
                return f"{iso_year}-W{iso_week:02d}"
            if level == "monthly":
                return f"{trade_date.year}-{trade_date.month:02d}"
            if level == "quarterly":
                return f"{trade_date.year}-Q{((trade_date.month - 1) // 3) + 1}"
            if level == "yearly":
                return f"{trade_date.year}"
            return "full_sample"

        levels = ["weekly", "monthly", "quarterly", "yearly", "overall"]
        summaries: dict[str, object] = {}
        for level in levels:
            bucketed_states: dict[str, list[BacktestDailyState]] = defaultdict(list)
            bucketed_signals: dict[str, list[dict]] = defaultdict(list)
            bucketed_trades: dict[str, list[BacktestTrade]] = defaultdict(list)
            for state in result.daily_states:
                bucketed_states[period_key(state.trade_date, level)].append(state)
            for row in result.signals:
                row_date = date.fromisoformat(row["trade_date"])
                bucketed_signals[period_key(row_date, level)].append(row)
            for trade in result.trades:
                trade_bucket_date = trade.exit_date or trade.entry_date
                bucketed_trades[period_key(trade_bucket_date, level)].append(trade)
            bucket_payload = []
            for label, states in sorted(bucketed_states.items()):
                trades = bucketed_trades.get(label, [])
                signals = bucketed_signals.get(label, [])
                bucket_payload.append(self._summarize_period_bucket(label, states, trades, signals))
            summaries[level] = bucket_payload
        return summaries

    def _summarize_period_bucket(self, label: str, states: list[BacktestDailyState], trades: list[BacktestTrade], signals: list[dict]) -> dict[str, object]:
        navs = [state.nav for state in states]
        if not navs:
            return {"label": label}
        returns = []
        for previous, current in zip(navs, navs[1:]):
            if previous > 0:
                returns.append((current / previous) - 1.0)
        avg_ret = sum(returns) / len(returns) if returns else 0.0
        variance = sum((value - avg_ret) ** 2 for value in returns) / len(returns) if returns else 0.0
        std_dev = sqrt(variance) if variance > 0 else 0.0
        downside = [value for value in returns if value < 0]
        downside_var = sum(value**2 for value in downside) / len(downside) if downside else 0.0
        downside_dev = sqrt(downside_var) if downside_var > 0 else 0.0
        peak = navs[0]
        max_drawdown = 0.0
        drawdown_duration = 0
        current_duration = 0
        for nav in navs:
            peak = max(peak, nav)
            drawdown = (nav / peak) - 1.0 if peak else 0.0
            if drawdown < 0:
                current_duration += 1
            else:
                current_duration = 0
            drawdown_duration = max(drawdown_duration, current_duration)
            max_drawdown = min(max_drawdown, drawdown)
        wins = [trade for trade in trades if trade.pnl > 0]
        losses = [trade for trade in trades if trade.pnl < 0]
        avg_win = sum(trade.pnl for trade in wins) / len(wins) if wins else 0.0
        avg_loss = abs(sum(trade.pnl for trade in losses) / len(losses)) if losses else 0.0
        gross_profit = sum(trade.pnl for trade in wins)
        gross_loss = abs(sum(trade.pnl for trade in losses))
        strategy_counter = Counter(row.get("selected_strategy", "unknown") for row in signals)
        by_symbol: dict[str, dict[str, float]] = {}
        for symbol in sorted({trade.symbol for trade in trades} | {row.get("symbol") for row in signals if row.get("symbol")}):
            symbol_trades = [trade for trade in trades if trade.symbol == symbol]
            symbol_signals = [row for row in signals if row.get("symbol") == symbol]
            symbol_wins = [trade for trade in symbol_trades if trade.pnl > 0]
            symbol_losses = [trade for trade in symbol_trades if trade.pnl < 0]
            symbol_gross_profit = sum(trade.gross_pnl for trade in symbol_trades if trade.gross_pnl > 0)
            symbol_gross_loss = abs(sum(trade.gross_pnl for trade in symbol_trades if trade.gross_pnl < 0))
            by_symbol[symbol] = {
                "trade_count": float(len(symbol_trades)),
                "win_rate": round(len(symbol_wins) / len(symbol_trades), 6) if symbol_trades else 0.0,
                "profit_factor": round((sum(trade.pnl for trade in symbol_wins) / abs(sum(trade.pnl for trade in symbol_losses))) if symbol_losses else float(len(symbol_wins)), 6) if symbol_trades else 0.0,
                "avg_holding_period_days": round(sum(trade.holding_period_days for trade in symbol_trades) / len(symbol_trades), 6) if symbol_trades else 0.0,
                "selected_strategy_mix": self._normalize_counter(Counter(row.get("selected_strategy", "unknown") for row in symbol_signals)),
                "gross_edge": round(symbol_gross_profit - symbol_gross_loss, 6),
                "net_edge": round(sum(trade.pnl for trade in symbol_trades), 6),
            }
        by_strategy: dict[str, dict[str, float]] = {}
        for strategy_name in sorted(strategy_counter):
            strategy_signals = [row for row in signals if row.get("selected_strategy") == strategy_name]
            by_strategy[strategy_name] = {
                "signal_count": float(len(strategy_signals)),
                "selection_share": round(len(strategy_signals) / len(signals), 6) if signals else 0.0,
            }
        return {
            "label": label,
            "start_date": states[0].trade_date.isoformat(),
            "end_date": states[-1].trade_date.isoformat(),
            "trading_days": len(states),
            "return_pct": round((navs[-1] / navs[0]) - 1.0, 6) if navs[0] > 0 else 0.0,
            "sharpe": round((avg_ret / std_dev * sqrt(252)) if std_dev > 0 else 0.0, 6),
            "sortino": round((avg_ret / downside_dev * sqrt(252)) if downside_dev > 0 else 0.0, 6),
            "trade_count": float(len(trades)),
            "turnover": float(len(trades)),
            "win_rate": round(len(wins) / len(trades), 6) if trades else 0.0,
            "payoff_ratio": round(avg_win / avg_loss, 6) if avg_loss > 0 else 0.0,
            "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss > 0 else round(gross_profit, 6),
            "avg_holding_period_days": round(sum(trade.holding_period_days for trade in trades) / len(trades), 6) if trades else 0.0,
            "max_drawdown": round(abs(max_drawdown), 6),
            "drawdown_duration_days": float(drawdown_duration),
            "gross_edge": round(sum(trade.gross_pnl for trade in trades), 6),
            "net_edge": round(sum(trade.pnl for trade in trades), 6),
            "selected_strategy_mix": self._normalize_counter(strategy_counter),
            "by_symbol": by_symbol,
            "by_strategy": by_strategy,
        }

    def _run_adaptive_portfolio(
        self,
        datasets: dict[str, ResearchDataset],
        candidate_signal_maps: dict[str, dict[str, list]],
        candidate_evaluations: dict[str, CandidateEvaluation],
        symbol_profiles: dict[str, dict],
    ) -> BacktestResult:
        all_dates = sorted({bar.trade_date for dataset in datasets.values() for bar in dataset.price_bars})
        bars_by_symbol = {
            symbol: {bar.trade_date: bar for bar in sorted(dataset.price_bars, key=lambda item: item.trade_date)}
            for symbol, dataset in datasets.items()
        }
        next_date_by_symbol = {
            symbol: self._next_date_lookup(sorted(dataset.price_bars, key=lambda item: item.trade_date))
            for symbol, dataset in datasets.items()
        }
        signal_lookup = {
            candidate_name: {
                symbol: {signal.trade_date: signal for signal in symbol_signals}
                for symbol, symbol_signals in symbol_map.items()
            }
            for candidate_name, symbol_map in candidate_signal_maps.items()
        }
        cost_model = CostModel(self.assumptions)
        cash = self.assumptions.initial_cash
        trades: list[BacktestTrade] = []
        daily_states: list[BacktestDailyState] = []
        signal_rows: list[dict] = []
        nav_series: list[float] = []
        heat_series: list[float] = []
        return_series: list[float] = []
        previous_nav = cash
        positions: dict[str, dict] = {}
        slot_block_reason_counts: Counter = Counter()

        for trade_date in all_dates:
            day_rows: list[dict] = []
            current_prices = {
                symbol: bars_by_symbol[symbol][trade_date].close
                for symbol in datasets
                if trade_date in bars_by_symbol[symbol]
            }
            pre_trade_exposure = sum(
                positions[symbol]["quantity"] * current_prices.get(symbol, positions[symbol]["avg_entry_price"])
                for symbol in positions
            )
            current_nav = cash + pre_trade_exposure

            for symbol in datasets:
                bar = bars_by_symbol[symbol].get(trade_date)
                if bar is None:
                    continue
                next_date = next_date_by_symbol[symbol].get(trade_date)
                next_bar = bars_by_symbol[symbol].get(next_date) if next_date else None
                candidate_signals = {
                    name: candidate_symbol_map[symbol][trade_date]
                    for name, candidate_symbol_map in signal_lookup.items()
                    if symbol in candidate_symbol_map and trade_date in candidate_symbol_map[symbol]
                }
                if not candidate_signals:
                    continue
                position = positions.get(symbol)
                selector = self._select_adaptive_strategy(candidate_signals, candidate_evaluations, position, bar)
                selected_signal = selector["signal"]
                selected_strategy = selector["selected_strategy"]
                profit_state = self._profit_state(position, bar.close)
                position_stage = self._position_stage(position)
                regime_deterioration_level = self._regime_deterioration_level(selected_signal)
                exit_policy = "NONE"
                exit_severity = "none"

                if position is not None:
                    position["highest_close"] = max(position["highest_close"], bar.close)
                    current_atr = float(getattr(selected_signal, "screening_details", {}).get("atr_14", max(bar.close * 0.02, 1.0)))
                    position["trailing_stop"] = max(position["trailing_stop"], position["highest_close"] - current_atr * position.get("atr_stop_multiplier", self.assumptions.atr_stop_multiplier))
                    exit_policy, exit_severity = self._adaptive_exit_policy(position, bar, selected_signal, profit_state, regime_deterioration_level)
                    if exit_policy == "EXIT_ON_HARD_RISK" and next_bar is not None:
                        trade_cost = cost_model.apply(next_bar.open, position["quantity"], "sell", adv_turnover=max(bar.turnover, 1.0))
                        cash += position["quantity"] * trade_cost.effective_price
                        self._close_open_tranches(trades, list(position["open_trade_indexes"]), next_bar.trade_date, trade_cost, "EXIT_FULL", exit_policy)
                        positions.pop(symbol, None)
                        position = None
                    elif exit_policy in {"REDUCE_ON_EXTENSION", "REDUCE_ON_REGIME_SOFTENING"} and next_bar is not None and len(position["open_trade_indexes"]) > 1:
                        trade_index = position["open_trade_indexes"].pop()
                        reduce_qty = trades[trade_index].quantity
                        trade_cost = cost_model.apply(next_bar.open, reduce_qty, "sell", adv_turnover=max(bar.turnover, 1.0))
                        cash += reduce_qty * trade_cost.effective_price
                        self._close_open_tranches(trades, [trade_index], next_bar.trade_date, trade_cost, "REDUCE_PARTIAL", exit_policy)
                        position["quantity"] -= reduce_qty
                    elif exit_policy in {"EXIT_ON_INVALIDATION", "EXIT_ON_TIME_DECAY"} and next_bar is not None:
                        trade_cost = cost_model.apply(next_bar.open, position["quantity"], "sell", adv_turnover=max(bar.turnover, 1.0))
                        cash += position["quantity"] * trade_cost.effective_price
                        self._close_open_tranches(trades, list(position["open_trade_indexes"]), next_bar.trade_date, trade_cost, "EXIT_FULL", exit_policy)
                        positions.pop(symbol, None)
                        position = None

                day_rows.append(
                    {
                        "symbol": symbol,
                        "trade_date": trade_date.isoformat(),
                        "selected_strategy": selected_strategy,
                        "selected_signal_state": selector.get("selected_signal_state", str(getattr(selected_signal, "state", "REJECT"))),
                        "selection_reason": selector["selection_reason"],
                        "selection_confidence": selector["selection_confidence"],
                        "selected_score_margin": selector.get("selected_score_margin", round(getattr(selected_signal, "score_margin", 0.0), 6)),
                        "candidate_actionability_rank": selector.get("candidate_actionability_rank", []),
                        "signal_state": str(getattr(selected_signal, "state", "REJECT")),
                        "candidate_reason_codes": list(getattr(selected_signal, "reasons", [])),
                        "composite_score": getattr(selected_signal, "composite_score", 0.0),
                        "screening_pass": getattr(selected_signal, "screening_pass", False),
                        "screening_blockers": list(getattr(selected_signal, "screening_blockers", [])),
                        "soft_blockers": list(getattr(selected_signal, "soft_blockers", [])),
                        "entry_band": getattr(selected_signal, "entry_band", "reject"),
                        "entry_blockers": list(getattr(selected_signal, "entry_blockers", [])),
                        "exit_policy": exit_policy,
                        "exit_severity": exit_severity,
                        "position_stage": position_stage,
                        "profit_state": profit_state,
                        "regime_deterioration_level": regime_deterioration_level,
                        "allocator_rank": None,
                        "allocator_blockers": [],
                        "slot_awarded": False,
                        "capital_requested": 0.0,
                        "capital_granted": 0.0,
                    }
                )

            signal_rows.extend(day_rows)
            current_exposure = sum(
                positions[symbol]["quantity"] * current_prices.get(symbol, positions[symbol]["avg_entry_price"])
                for symbol in positions
            )
            current_nav = cash + current_exposure
            deployable_capital = current_nav * self.assumptions.max_portfolio_heat
            available_slots = max(self.assumptions.max_active_positions - len(positions), 0)
            entry_candidates = sorted(
                [
                    row
                    for row in day_rows
                    if row["signal_state"] in {"ENTER_PARTIAL", "ADD_PARTIAL"}
                ],
                key=lambda row: (
                    self._entry_band_priority(row.get("entry_band")),
                    row.get("selected_score_margin", 0.0),
                    row["selection_confidence"],
                    row["composite_score"],
                ),
                reverse=True,
            )
            for rank_index, row in enumerate(entry_candidates, start=1):
                row["allocator_rank"] = rank_index
                row["concurrent_opportunity_count"] = len(entry_candidates)
                symbol = row["symbol"]
                if current_exposure >= deployable_capital:
                    slot_block_reason_counts["portfolio_heat_cap"] += 1
                    row["allocator_blockers"].append("portfolio_heat_cap")
                    break
                bar = bars_by_symbol[symbol].get(trade_date)
                next_date = next_date_by_symbol[symbol].get(trade_date)
                next_bar = bars_by_symbol[symbol].get(next_date) if next_date else None
                if bar is None or next_bar is None:
                    slot_block_reason_counts["missing_next_bar"] += 1
                    row["allocator_blockers"].append("missing_next_bar")
                    continue
                candidate_signals = {
                    name: candidate_symbol_map[symbol][trade_date]
                    for name, candidate_symbol_map in signal_lookup.items()
                    if symbol in candidate_symbol_map and trade_date in candidate_symbol_map[symbol]
                }
                selected_signal = candidate_signals.get(row["selected_strategy"])
                if selected_signal is None:
                    slot_block_reason_counts["missing_selected_signal"] += 1
                    row["allocator_blockers"].append("missing_selected_signal")
                    continue
                position = positions.get(symbol)
                is_enter = row["signal_state"] == "ENTER_PARTIAL" and position is None
                is_add = row["signal_state"] == "ADD_PARTIAL" and position is not None and self._can_add_position(position, selected_signal, bar)
                if is_enter and available_slots <= 0:
                    slot_block_reason_counts["no_available_slots"] += 1
                    row["allocator_blockers"].append("no_available_slots")
                    continue
                if not is_enter and not is_add:
                    slot_block_reason_counts["invalid_entry_state"] += 1
                    row["allocator_blockers"].append("invalid_entry_state")
                    continue
                tranche_fraction = 0.30 if is_enter else 0.20
                target_notional = min(
                    current_nav * self.assumptions.max_symbol_weight * tranche_fraction,
                    max(deployable_capital - current_exposure, 0.0),
                    cash,
                )
                row["capital_requested"] = round(target_notional, 6)
                quantity = int(target_notional / max(next_bar.open, 1.0))
                if quantity <= 0:
                    slot_block_reason_counts["quantity_zero"] += 1
                    row["allocator_blockers"].append("quantity_zero")
                    continue
                trade_cost = cost_model.apply(next_bar.open, quantity, "buy", adv_turnover=max(bar.turnover, 1.0))
                total_cash_need = quantity * trade_cost.effective_price
                if total_cash_need > cash:
                    slot_block_reason_counts["cash_insufficient"] += 1
                    row["allocator_blockers"].append("cash_insufficient")
                    continue
                cash -= total_cash_need
                if is_enter:
                    available_slots -= 1
                    positions[symbol] = {
                        "quantity": 0,
                        "entry_price": trade_cost.effective_price,
                        "entry_date": next_bar.trade_date,
                        "highest_close": next_bar.close,
                        "trailing_stop": trade_cost.effective_price - float(getattr(selected_signal, "screening_details", {}).get("atr_14", max(next_bar.close * 0.02, 1.0))) * self._symbol_atr_multiplier(symbol_profiles.get(symbol, {})),
                        "atr_stop_multiplier": self._symbol_atr_multiplier(symbol_profiles.get(symbol, {})),
                        "avg_entry_price": trade_cost.effective_price,
                        "open_trade_indexes": [],
                    }
                trades.append(
                    BacktestTrade(
                        symbol=symbol,
                        entry_date=next_bar.trade_date,
                        exit_date=None,
                        entry_price=trade_cost.effective_price,
                        exit_price=None,
                        quantity=quantity,
                        pnl=0.0,
                        decision={
                            "decision": "ADD_PARTIAL" if is_add else "ENTER_PARTIAL",
                            "trade_date": trade_date.isoformat(),
                            "reason_codes": list(selected_signal.reasons),
                            "cost_breakdown": trade_cost.cost_breakdown,
                            "tranche_number": len(positions[symbol]["open_trade_indexes"]) + 1,
                            "symbol_tags": symbol_profiles.get(symbol, {}).get("tags", []),
                            "selected_strategy": row["selected_strategy"],
                            "selection_reason": row["selection_reason"],
                        },
                        total_cost=trade_cost.total_cost,
                    )
                )
                positions[symbol]["open_trade_indexes"].append(len(trades) - 1)
                positions[symbol]["quantity"] = sum(trades[index].quantity for index in positions[symbol]["open_trade_indexes"])
                positions[symbol]["avg_entry_price"] = self._avg_entry_price(trades, positions[symbol]["open_trade_indexes"])
                current_exposure += quantity * next_bar.open
                row["slot_awarded"] = True
                row["capital_granted"] = round(total_cash_need, 6)
                row["concurrent_positions_opened"] = len(positions)

            prices = {
                symbol: bars_by_symbol[symbol].get(trade_date, SimpleNamespace(close=positions[symbol]["avg_entry_price"])).close
                for symbol in positions
            }
            exposure = sum(positions[symbol]["quantity"] * prices[symbol] for symbol in positions)
            nav = cash + exposure
            heat = exposure / nav if nav > 0 else 0.0
            nav_series.append(nav)
            heat_series.append(heat)
            if previous_nav > 0:
                return_series.append((nav / previous_nav) - 1.0)
            previous_nav = nav
            selected_mix = Counter(row["selected_strategy"] for row in day_rows)
            daily_states.append(
                BacktestDailyState(
                    trade_date=trade_date,
                    cash=round(cash, 3),
                    position_qty={symbol: pos["quantity"] for symbol, pos in positions.items()},
                    close_price={symbol: round(price, 3) for symbol, price in prices.items()},
                    nav=round(nav, 3),
                    regime_label="MULTI_ASSET_ADAPTIVE",
                    signal_state="PORTFOLIO",
                    portfolio_heat=round(heat, 6),
                    exposure=round(exposure, 3),
                    selected_strategy=", ".join(f"{name}:{count}" for name, count in sorted(selected_mix.items())),
                    exit_policy=self._dominant_exit_policy(day_rows),
                )
            )

        for symbol, position in list(positions.items()):
            last_date = max(date_ for date_ in bars_by_symbol[symbol].keys())
            last_bar = bars_by_symbol[symbol][last_date]
            total_qty = sum(trades[index].quantity for index in position["open_trade_indexes"])
            trade_cost = cost_model.apply(last_bar.close, total_qty, "sell", adv_turnover=max(last_bar.turnover, 1.0))
            cash += total_qty * trade_cost.effective_price
            self._close_open_tranches(trades, list(position["open_trade_indexes"]), last_date, trade_cost, "EXIT_FULL", "FINAL_MARK_TO_MARKET")

        if daily_states:
            daily_states[-1].cash = round(cash, 3)
            daily_states[-1].nav = round(cash, 3)
            daily_states[-1].portfolio_heat = 0.0
            daily_states[-1].exposure = 0.0
            nav_series[-1] = cash
            heat_series[-1] = 0.0

        symbol_recommendations = self._symbol_recommendations(trades, symbol_profiles, signal_rows, datasets)
        selected_counts = Counter(row["selected_strategy"] for row in signal_rows)
        hal_selected_counts = Counter(row["selected_strategy"] for row in signal_rows if row["symbol"] == "HAL")
        concurrent_usage = self._concurrent_usage_metrics(daily_states)
        summary = BacktestSummary(
            run_id="research-portfolio",
            symbol="PORTFOLIO",
            metrics=WalkForwardBacktestEngine(self.assumptions)._build_metrics(nav_series, return_series, trades, heat_series),
            assumptions=asdict(self.assumptions),
        )
        summary.metrics.update(concurrent_usage)
        return BacktestResult(
            summary=summary,
            trades=trades,
            daily_states=daily_states,
            signals=signal_rows,
            dataset_report={
                "symbols": list(datasets.keys()),
                "assumptions_applied": ["adaptive_switch", "portfolio_heat_cap", "config_driven_costs", "next_session_execution", "staged_entries", "partial_exits"],
                "symbol_recommendations": symbol_recommendations,
                "average_tranches_per_position": round(sum(item["avg_tranches"] for item in symbol_recommendations.values()) / len(symbol_recommendations), 3) if symbol_recommendations else 0.0,
                "current_selected_hal_strategy": max(hal_selected_counts, key=hal_selected_counts.get) if hal_selected_counts else "n/a",
                "current_exit_policy_behavior": self._dominant_exit_policy(signal_rows),
                "selected_strategy_mix": self._normalize_counter(selected_counts),
                "concurrent_usage": concurrent_usage,
                "deployment_summary": concurrent_usage,
                "slot_block_reason_counts": dict(slot_block_reason_counts),
                "entry_blocker_counts": dict(Counter(blocker for row in signal_rows for blocker in row.get("entry_blockers", []))),
                "screening_summary": {
                    symbol: {
                        "screening_pass_rate": payload.get("screening_pass_rate", 0.0),
                        "actionable_signal_rate": payload.get("actionable_signal_rate", 0.0),
                        "trade_conversion_rate": payload.get("trade_conversion_rate", 0.0),
                    }
                    for symbol, payload in symbol_recommendations.items()
                },
                "symbol_health_diagnostics": symbol_recommendations,
                "module_decisions": {
                    "event_drift": {
                        "enabled": any(row["selected_strategy"] == "franchise_event_drift" for row in signal_rows),
                        "reason": "bounded event window" if any(row["selected_strategy"] == "franchise_event_drift" for row in signal_rows) else "event overlay not selected by adaptive switch",
                    },
                    "seasonality": {
                        "enabled": any(row["selected_strategy"] == "franchise_seasonality_enabled" for row in signal_rows),
                        "reason": "validated selector preference" if any(row["selected_strategy"] == "franchise_seasonality_enabled" for row in signal_rows) else "not validated",
                    },
                },
            },
        )

    def _target_quantity(self, cash: float, open_price: float, tranche_fraction: float) -> int:
        notional_cap = cash * min(self.assumptions.max_portfolio_heat, self.assumptions.max_symbol_weight) * tranche_fraction
        return int(min(notional_cap, cash) / max(open_price, 1.0))

    def _avg_entry_price(self, trades: list[BacktestTrade], open_trade_indexes: list[int]) -> float:
        total_qty = sum(trades[index].quantity for index in open_trade_indexes)
        if total_qty <= 0:
            return 0.0
        return sum(trades[index].entry_price * trades[index].quantity for index in open_trade_indexes) / total_qty

    def _profit_state(self, position: dict | None, close_price: float) -> str:
        if position is None:
            return "flat"
        pnl_pct = (close_price / max(position["avg_entry_price"], 1e-6)) - 1.0
        if pnl_pct >= 0.10:
            return "extended_winner"
        if pnl_pct > 0.0:
            return "winner"
        if pnl_pct > -0.01:
            return "flat_to_slight_loss"
        return "loser"

    def _position_stage(self, position: dict | None) -> str:
        if position is None:
            return "empty"
        tranche_count = len(position["open_trade_indexes"])
        if tranche_count <= 1:
            return "core"
        if tranche_count == 2:
            return "built"
        return "extended"

    def _regime_deterioration_level(self, signal) -> str:
        reasons = set(getattr(signal, "reasons", []))
        if "REGIME_NOT_SUPPORTIVE" in reasons:
            return "hard"
        if "SCORE_BELOW_HOLD" in reasons:
            return "soft"
        return "none"

    def _adaptive_exit_policy(self, position: dict, bar, signal, profit_state: str, regime_deterioration_level: str) -> tuple[str, str]:
        if bar.close <= position["trailing_stop"]:
            return "EXIT_ON_HARD_RISK", "hard"
        signal_state = str(getattr(signal, "state", "HOLD"))
        holding_days = max((bar.trade_date - position["entry_date"]).days, 0)
        if signal_state == "EXIT_FULL" and regime_deterioration_level == "hard":
            return "EXIT_ON_INVALIDATION", "hard"
        if signal_state == "EXIT_FULL" and holding_days >= self.assumptions.time_stop_bars:
            return "EXIT_ON_TIME_DECAY", "medium"
        if signal_state == "REDUCE_PARTIAL" and profit_state == "extended_winner":
            return "REDUCE_ON_EXTENSION", "soft"
        if signal_state == "REDUCE_PARTIAL" and profit_state == "winner" and len(position.get("open_trade_indexes", [])) > 1:
            return "REDUCE_ON_EXTENSION", "soft"
        if signal_state in {"REDUCE_PARTIAL", "EXIT_FULL"} and regime_deterioration_level == "soft":
            return "REDUCE_ON_REGIME_SOFTENING", "soft"
        if signal_state in {"EXIT_FULL", "REDUCE_PARTIAL"} and profit_state in {"winner", "extended_winner"}:
            return "HOLD_WEAKNESS", "soft"
        return "HOLD_CORE", "none"

    def _can_add_position(self, position: dict, signal, bar) -> bool:
        if len(position["open_trade_indexes"]) >= 2:
            return False
        module_scores = getattr(signal, "module_scores", {})
        breakout_confirmation = module_scores.get("breakout_confirmation", 0.0)
        pullback_quality = module_scores.get("pullback", 0.0)
        long_trend_quality = module_scores.get("long_trend_quality", 0.0)
        extended = (bar.close / max(position["avg_entry_price"], 1e-6)) - 1.0 > 0.08
        if extended:
            return False
        if long_trend_quality == 0.0 and breakout_confirmation == 0.0 and pullback_quality == 0.0:
            return getattr(signal, "composite_score", 0.0) >= getattr(signal, "threshold", 0.0) + 0.03
        return long_trend_quality >= 0.65 and (breakout_confirmation >= 0.70 or pullback_quality >= 0.72) and getattr(signal, "composite_score", 0.0) >= getattr(signal, "threshold", 0.0) + 0.03

    def _select_adaptive_strategy(self, candidate_signals: dict[str, object], candidate_evaluations: dict[str, CandidateEvaluation], position: dict | None, bar) -> dict[str, object]:
        breakout = candidate_signals.get("franchise_breakout_confirmed")
        pullback = candidate_signals.get("franchise_pullback_accumulator")
        risk = candidate_signals.get("franchise_risk_managed")
        event = candidate_signals.get("franchise_event_drift")
        ranked_candidates: list[tuple[tuple[float, float, float, float], str, object, str]] = []

        def add_rank(candidate_name: str, signal, reason: str, preference_weight: float) -> None:
            if signal is None:
                return
            ranked_candidates.append(
                (
                    (
                        float(self._signal_state_priority(str(getattr(signal, "state", "REJECT")))),
                        float(self._entry_band_priority(getattr(signal, "entry_band", "reject"))),
                        float(getattr(signal, "score_margin", 0.0)),
                        preference_weight,
                    ),
                    candidate_name,
                    signal,
                    reason,
                )
            )

        if position is not None and risk is not None and getattr(risk, "module_scores", {}).get("risk_penalty", 0.0) >= 0.12 and str(getattr(risk, "state", "REJECT")) != "REJECT":
            add_rank("franchise_risk_managed", risk, "elevated_volatility_existing_position", 1.1)
        if (
            event is not None
            and getattr(event, "module_scores", {}).get("event_drift", 0.0) >= 0.70
            and getattr(event, "module_scores", {}).get("breakout_confirmation", 0.0) >= 0.72
            and getattr(event, "module_scores", {}).get("relative_strength", 0.0) >= 0.60
            and str(getattr(event, "state", "REJECT")) in {"ENTER_PARTIAL", "ADD_PARTIAL"}
        ):
            add_rank("franchise_event_drift", event, "bounded_event_window", 1.05)
        if breakout is not None and getattr(breakout, "module_scores", {}).get("breakout_confirmation", 0.0) >= 0.62 and getattr(breakout, "module_scores", {}).get("relative_strength", 0.0) >= 0.55 and str(getattr(breakout, "state", "REJECT")) != "REJECT":
            add_rank("franchise_breakout_confirmed", breakout, "high_breakout_confirmation", 1.0)
        if pullback is not None and getattr(pullback, "module_scores", {}).get("pullback", 0.0) >= 0.60 and getattr(pullback, "module_scores", {}).get("long_trend_quality", 0.0) >= 0.60 and str(getattr(pullback, "state", "REJECT")) != "REJECT":
            add_rank("franchise_pullback_accumulator", pullback, "constructive_pullback_in_trend", 0.95)
        if ranked_candidates:
            ranked_candidates.sort(key=lambda item: item[0], reverse=True)
            _, selected_name, selected_signal, selection_reason = ranked_candidates[0]
            return {
                "selected_strategy": selected_name,
                "signal": selected_signal,
                "selection_reason": selection_reason,
                "selection_confidence": round(
                    (
                        max(getattr(selected_signal, "module_scores", {}).get("breakout_confirmation", 0.0), getattr(selected_signal, "module_scores", {}).get("pullback", 0.0))
                        + getattr(selected_signal, "module_scores", {}).get("relative_strength", 0.0)
                    ) / 2.0,
                    3,
                ),
                "selected_signal_state": str(getattr(selected_signal, "state", "REJECT")),
                "selected_score_margin": round(getattr(selected_signal, "score_margin", 0.0), 6),
                "candidate_actionability_rank": [
                    {
                        "candidate": candidate_name,
                        "signal_state": str(getattr(signal, "state", "REJECT")),
                        "entry_band": getattr(signal, "entry_band", "reject"),
                        "score_margin": round(getattr(signal, "score_margin", 0.0), 6),
                    }
                    for _, candidate_name, signal, _ in ranked_candidates
                ],
            }
        fallback_order = [
            "franchise_breakout_confirmed",
            "franchise_pullback_accumulator",
            "franchise_risk_managed",
            "franchise_event_drift",
        ]
        fallback_name = next(
            (
                candidate_name
                for candidate_name in fallback_order
                if candidate_name in candidate_signals and str(getattr(candidate_signals[candidate_name], "state", "REJECT")) != "REJECT"
            ),
            None,
        )
        if fallback_name is None:
            most_promising = self._metric_leaders(candidate_evaluations).get("most_promising_candidate")
            fallback_name = next(
                (
                    candidate_name
                    for candidate_name in [most_promising, *candidate_signals.keys()]
                    if candidate_name and candidate_name != "franchise_seasonality_enabled"
                ),
                next(iter(candidate_signals.keys())),
            )
        return {
            "selected_strategy": fallback_name,
            "signal": candidate_signals[fallback_name],
            "selection_reason": "fallback_to_most_promising_candidate",
            "selection_confidence": 0.5,
            "selected_signal_state": str(getattr(candidate_signals[fallback_name], "state", "REJECT")),
            "selected_score_margin": round(getattr(candidate_signals[fallback_name], "score_margin", 0.0), 6),
            "candidate_actionability_rank": [],
        }

    def _dominant_exit_policy(self, signal_rows: list[dict]) -> str:
        counts: dict[str, int] = {}
        for row in signal_rows:
            policy = row.get("exit_policy")
            if policy and policy != "NONE":
                counts[policy] = counts.get(policy, 0) + 1
        return max(counts, key=counts.get) if counts else "NONE"

    def _run_portfolio(self, datasets: dict[str, ResearchDataset], signal_map_by_symbol: dict[str, list], symbol_profiles: dict[str, dict]) -> BacktestResult:
        all_dates = sorted({bar.trade_date for dataset in datasets.values() for bar in dataset.price_bars})
        bars_by_symbol = {symbol: {bar.trade_date: bar for bar in sorted(dataset.price_bars, key=lambda item: item.trade_date)} for symbol, dataset in datasets.items()}
        next_date_by_symbol = {symbol: self._next_date_lookup(sorted(dataset.price_bars, key=lambda item: item.trade_date)) for symbol, dataset in datasets.items()}
        signal_lookup = {symbol: {signal.trade_date: signal for signal in signals} for symbol, signals in signal_map_by_symbol.items()}
        cost_model = CostModel(self.assumptions)
        positions: dict[str, dict] = {}
        cash = self.assumptions.initial_cash
        trades: list[BacktestTrade] = []
        daily_states: list[BacktestDailyState] = []
        signal_rows: list[dict] = []
        nav_series: list[float] = []
        heat_series: list[float] = []
        return_series: list[float] = []
        previous_nav = cash

        for trade_date in all_dates:
            exit_symbols: list[str] = []
            for symbol, position in list(positions.items()):
                bar = bars_by_symbol[symbol].get(trade_date)
                signal = signal_lookup.get(symbol, {}).get(trade_date)
                if bar is None:
                    continue
                position["highest_close"] = max(position["highest_close"], bar.close)
                position["trailing_stop"] = max(position["trailing_stop"], position["highest_close"] - 2.0 * self.assumptions.atr_stop_multiplier)
                open_trades = [trades[index] for index in position["open_trade_indexes"]]
                total_qty = sum(item.quantity for item in open_trades)
                position["quantity"] = total_qty
                if open_trades:
                    position["avg_entry_price"] = sum(item.entry_price * item.quantity for item in open_trades) / total_qty

                if bar.close <= position["trailing_stop"] or (signal and str(signal.state) in {"EXIT", "EXIT_FULL"}):
                    next_date = next_date_by_symbol[symbol].get(trade_date)
                    next_bar = bars_by_symbol[symbol].get(next_date) if next_date else None
                    if next_bar is None or total_qty <= 0:
                        continue
                    trade_cost = cost_model.apply(next_bar.open, total_qty, "sell", adv_turnover=max(bar.turnover, 1.0))
                    cash += total_qty * trade_cost.effective_price
                    self._close_open_tranches(trades, list(position["open_trade_indexes"]), next_date, trade_cost, "EXIT_FULL", "EXIT_FULL")
                    exit_symbols.append(symbol)
                elif signal and str(signal.state) == "REDUCE_PARTIAL" and len(position["open_trade_indexes"]) > 1:
                    next_date = next_date_by_symbol[symbol].get(trade_date)
                    next_bar = bars_by_symbol[symbol].get(next_date) if next_date else None
                    if next_bar is None:
                        continue
                    trade_index = position["open_trade_indexes"].pop()
                    reduce_qty = trades[trade_index].quantity
                    trade_cost = cost_model.apply(next_bar.open, reduce_qty, "sell", adv_turnover=max(bar.turnover, 1.0))
                    cash += reduce_qty * trade_cost.effective_price
                    self._close_open_tranches(trades, [trade_index], next_date, trade_cost, "REDUCE_PARTIAL", "REDUCE_PARTIAL")
                    position["partial_exit_count"] += 1
                elif len(position["open_trade_indexes"]) > 1 and not position["profit_extension_taken"] and bar.close >= position["avg_entry_price"] * 1.12:
                    next_date = next_date_by_symbol[symbol].get(trade_date)
                    next_bar = bars_by_symbol[symbol].get(next_date) if next_date else None
                    if next_bar is None:
                        continue
                    trade_index = position["open_trade_indexes"].pop()
                    reduce_qty = trades[trade_index].quantity
                    trade_cost = cost_model.apply(next_bar.open, reduce_qty, "sell", adv_turnover=max(bar.turnover, 1.0))
                    cash += reduce_qty * trade_cost.effective_price
                    self._close_open_tranches(trades, [trade_index], next_date, trade_cost, "REDUCE_PARTIAL", "PROFIT_EXTENSION")
                    position["partial_exit_count"] += 1
                    position["profit_extension_taken"] = True

            for symbol in exit_symbols:
                positions.pop(symbol, None)

            ranked_entries = []
            for symbol, signals in signal_lookup.items():
                signal = signals.get(trade_date)
                bar = bars_by_symbol[symbol].get(trade_date)
                if signal and str(signal.state) in {"ENTER", "ENTER_PARTIAL", "ADD_PARTIAL"} and bar is not None:
                    ranked_entries.append((signal.composite_score, symbol, signal, bar))
                    signal_rows.append(
                        {
                            "symbol": symbol,
                            "trade_date": trade_date.isoformat(),
                            "candidate_reason_codes": list(signal.reasons),
                            "composite_score": signal.composite_score,
                            "signal_state": str(signal.state),
                        }
                    )
            ranked_entries.sort(reverse=True)

            current_nav = cash + sum(pos["quantity"] * bars_by_symbol[sym].get(trade_date, SimpleNamespace(close=pos["entry_price"])).close for sym, pos in positions.items())
            deployable_capital = current_nav * self.assumptions.max_portfolio_heat
            available_slots = max(self.assumptions.max_active_positions - len(positions), 0)
            current_exposure = sum(pos["quantity"] * bars_by_symbol[sym].get(trade_date, SimpleNamespace(close=pos["entry_price"])).close for sym, pos in positions.items())

            for _, symbol, signal, bar in ranked_entries:
                next_date = next_date_by_symbol[symbol].get(trade_date)
                next_bar = bars_by_symbol[symbol].get(next_date) if next_date else None
                if next_bar is None:
                    continue
                is_add = symbol in positions and str(signal.state) == "ADD_PARTIAL"
                is_enter = symbol not in positions and str(signal.state) in {"ENTER", "ENTER_PARTIAL"}
                if not is_enter and not is_add:
                    continue
                if is_enter and available_slots <= 0:
                    continue
                if current_exposure >= deployable_capital:
                    break
                current_open_count = len(positions[symbol]["open_trade_indexes"]) if symbol in positions else 0
                tranche_fraction = 0.40 if current_open_count == 0 else 0.30
                target_notional = min(
                    current_nav * self.assumptions.max_symbol_weight * tranche_fraction,
                    max(deployable_capital - current_exposure, 0.0),
                    cash,
                )
                quantity = int(target_notional / max(next_bar.open, 1.0))
                if quantity <= 0:
                    continue
                trade_cost = cost_model.apply(next_bar.open, quantity, "buy", adv_turnover=max(bar.turnover, 1.0))
                total_cash_need = quantity * trade_cost.effective_price
                if total_cash_need > cash:
                    continue
                cash -= total_cash_need
                if is_enter:
                    available_slots -= 1
                    positions[symbol] = {
                        "quantity": 0,
                        "entry_price": trade_cost.effective_price,
                        "entry_date": next_date,
                        "highest_close": next_bar.close,
                        "trailing_stop": trade_cost.effective_price - 2.0 * self.assumptions.atr_stop_multiplier,
                        "avg_entry_price": trade_cost.effective_price,
                        "open_trade_indexes": [],
                        "partial_exit_count": 0,
                        "profit_extension_taken": False,
                    }
                trades.append(
                    BacktestTrade(
                        symbol=symbol,
                        entry_date=next_date,
                        exit_date=None,
                        entry_price=trade_cost.effective_price,
                        exit_price=None,
                        quantity=quantity,
                        pnl=0.0,
                        decision={
                            "decision": "ADD_PARTIAL" if is_add else "ENTER_PARTIAL",
                            "trade_date": trade_date.isoformat(),
                            "reason_codes": list(signal.reasons),
                            "cost_breakdown": trade_cost.cost_breakdown,
                            "tranche_number": current_open_count + 1,
                            "symbol_tags": symbol_profiles.get(symbol, {}).get("tags", []),
                        },
                        total_cost=trade_cost.total_cost,
                    )
                )
                positions[symbol]["open_trade_indexes"].append(len(trades) - 1)
                open_trades = [trades[index] for index in positions[symbol]["open_trade_indexes"]]
                positions[symbol]["quantity"] = sum(item.quantity for item in open_trades)
                positions[symbol]["avg_entry_price"] = sum(item.entry_price * item.quantity for item in open_trades) / positions[symbol]["quantity"]
                current_exposure += quantity * next_bar.open

            prices = {symbol: bars_by_symbol[symbol].get(trade_date, SimpleNamespace(close=pos["entry_price"])).close for symbol, pos in positions.items()}
            exposure = sum(pos["quantity"] * prices[symbol] for symbol, pos in positions.items())
            nav = cash + exposure
            heat = exposure / nav if nav > 0 else 0.0
            nav_series.append(nav)
            heat_series.append(heat)
            if previous_nav > 0:
                return_series.append((nav / previous_nav) - 1.0)
            previous_nav = nav
            daily_states.append(
                BacktestDailyState(
                    trade_date=trade_date,
                    cash=round(cash, 3),
                    position_qty={symbol: pos["quantity"] for symbol, pos in positions.items()},
                    close_price={symbol: round(price, 3) for symbol, price in prices.items()},
                    nav=round(nav, 3),
                    regime_label="MULTI_ASSET",
                    signal_state="PORTFOLIO",
                    portfolio_heat=round(heat, 6),
                    exposure=round(exposure, 3),
                )
            )

        for symbol, position in list(positions.items()):
            last_date = max(date_ for date_ in bars_by_symbol[symbol].keys())
            last_bar = bars_by_symbol[symbol][last_date]
            total_qty = sum(trades[index].quantity for index in position["open_trade_indexes"])
            trade_cost = cost_model.apply(last_bar.close, total_qty, "sell", adv_turnover=max(last_bar.turnover, 1.0))
            cash += total_qty * trade_cost.effective_price
            self._close_open_tranches(trades, list(position["open_trade_indexes"]), last_date, trade_cost, "EXIT_FULL", "FINAL_MARK_TO_MARKET")

        symbol_recommendations = self._symbol_recommendations(trades, symbol_profiles)
        summary = BacktestSummary(
            run_id="research-portfolio",
            symbol="PORTFOLIO",
            metrics=WalkForwardBacktestEngine(self.assumptions)._build_metrics(nav_series, return_series, trades, heat_series),
            assumptions=asdict(self.assumptions),
        )
        return BacktestResult(
            summary=summary,
            trades=trades,
            daily_states=daily_states,
            signals=signal_rows,
            dataset_report={
                "symbols": list(datasets.keys()),
                "assumptions_applied": ["portfolio_heat_cap", "config_driven_costs", "next_session_execution", "staged_entries", "partial_exits"],
                "symbol_recommendations": symbol_recommendations,
                "average_tranches_per_position": round(sum(item["avg_tranches"] for item in symbol_recommendations.values()) / len(symbol_recommendations), 3) if symbol_recommendations else 0.0,
            },
        )

    def _close_open_tranches(self, trades: list[BacktestTrade], trade_indexes: list[int], exit_date: date, trade_cost, decision_label: str, exit_reason: str) -> None:
        total_qty = sum(trades[index].quantity for index in trade_indexes)
        allocated_cost = 0.0
        for offset, index in enumerate(trade_indexes):
            trade = trades[index]
            cost_share = trade_cost.total_cost * (trade.quantity / total_qty) if total_qty > 0 else 0.0
            if offset == len(trade_indexes) - 1:
                cost_share = trade_cost.total_cost - allocated_cost
            allocated_cost += cost_share
            trade.exit_date = exit_date
            trade.exit_price = trade_cost.effective_price
            trade.holding_period_days = max((exit_date - trade.entry_date).days, 0)
            trade.gross_pnl = round((trade.exit_price - trade.entry_price) * trade.quantity, 3)
            trade.total_cost = round(trade.total_cost + cost_share, 3)
            trade.pnl = round(trade.gross_pnl - trade.total_cost, 3)
            trade.decision = {**trade.decision, "exit_decision": decision_label, "exit_reason": exit_reason, "exit_policy": exit_reason}

    def _next_date_lookup(self, bars) -> dict[date, date]:
        dates = [bar.trade_date for bar in bars]
        return {current: nxt for current, nxt in zip(dates, dates[1:])}

    def _symbol_recommendations(
        self,
        trades: list[BacktestTrade],
        symbol_profiles: dict[str, dict],
        signal_rows: list[dict] | None = None,
        datasets: dict[str, ResearchDataset] | None = None,
    ) -> dict[str, dict]:
        grouped: dict[str, list[BacktestTrade]] = {}
        for trade in trades:
            grouped.setdefault(trade.symbol, []).append(trade)
        signal_rows = signal_rows or []
        signal_grouped: dict[str, list[dict]] = {}
        for row in signal_rows:
            signal_grouped.setdefault(row.get("symbol", "UNKNOWN"), []).append(row)
        recommendations: dict[str, dict] = {}
        all_symbols = sorted(set(grouped) | set(signal_grouped) | set((datasets or {}).keys()) | set(symbol_profiles.keys()))
        for symbol in all_symbols:
            symbol_trades = grouped.get(symbol, [])
            symbol_signal_rows = signal_grouped.get(symbol, [])
            closed = [trade for trade in symbol_trades if trade.exit_date is not None]
            wins = [trade for trade in closed if trade.pnl > 0]
            losses = [trade for trade in closed if trade.pnl < 0]
            net = sum(trade.pnl for trade in closed)
            gross = sum(trade.gross_pnl for trade in closed)
            avg_hold = sum(trade.holding_period_days for trade in closed) / len(closed) if closed else 0.0
            avg_tranches = sum(1 for trade in symbol_trades if trade.decision.get("decision") in {"ENTER_PARTIAL", "ADD_PARTIAL"}) / max(len(closed), 1)
            profit_factor = (sum(trade.pnl for trade in wins) / abs(sum(trade.pnl for trade in losses))) if losses else float(len(wins))
            tags = symbol_profiles.get(symbol, {}).get("tags", [])
            actionable_signals = [
                row for row in symbol_signal_rows if row.get("signal_state") in {"ENTER_PARTIAL", "ADD_PARTIAL", "HOLD"}
            ]
            screening_pass_count = sum(1 for row in symbol_signal_rows if row.get("screening_pass"))
            hard_risk_exits = sum(1 for trade in closed if trade.decision.get("exit_policy") == "EXIT_ON_HARD_RISK")
            blocker_counter = Counter()
            for row in symbol_signal_rows:
                blocker_counter.update(row.get("screening_blockers", []))
                blocker_counter.update(row.get("entry_blockers", []))
                if not row.get("screening_pass") and not row.get("screening_blockers"):
                    blocker_counter.update(row.get("candidate_reason_codes", []))
            dataset = (datasets or {}).get(symbol)
            if dataset is not None and not dataset.price_bars:
                recommendation = "data_problem"
            elif not closed and len(actionable_signals) == 0:
                recommendation = "ghost_no_signals"
            elif net > 0 and avg_hold >= self.assumptions.min_avg_holding_period_days and "dominant_franchise" in tags:
                recommendation = "accumulate-only"
            elif net > 0 and avg_hold >= self.assumptions.min_avg_holding_period_days:
                recommendation = "retain"
            elif avg_tranches > 1.2 and avg_hold >= self.assumptions.min_avg_holding_period_days:
                recommendation = "breakout-only"
            elif net < 0 and avg_hold < self.assumptions.min_avg_holding_period_days:
                recommendation = "exclude"
            else:
                recommendation = "down-rank"
            if recommendation == "data_problem":
                repair_mode = "data_problem"
            elif recommendation == "ghost_no_signals":
                repair_mode = "threshold_relaxation_needed"
            elif hard_risk_exits >= max(1, len(closed) // 2) and avg_hold < self.assumptions.min_avg_holding_period_days:
                repair_mode = "stop_too_tight"
            elif net < 0 and symbol_signal_rows and self._normalize_counter(Counter(row.get("selected_strategy", "unknown") for row in symbol_signal_rows)).get("franchise_pullback_accumulator", 0.0) > 0.7:
                repair_mode = "selector_misalignment"
            elif net < 0:
                repair_mode = "true_no_fit"
            else:
                repair_mode = "threshold_relaxation_needed" if len(actionable_signals) < max(1, len(symbol_signal_rows) * 0.05) else "selector_misalignment"
            recommendations[symbol] = {
                "first_available_date": dataset.dataset_report.first_available_date.isoformat() if dataset and getattr(dataset.dataset_report, "first_available_date", None) else None,
                "last_available_date": dataset.dataset_report.last_available_date.isoformat() if dataset and getattr(dataset.dataset_report, "last_available_date", None) else None,
                "signal_count": len(symbol_signal_rows),
                "actionable_signal_count": len(actionable_signals),
                "executed_trade_count": len(closed),
                "gross_contribution": round(gross, 3),
                "net_contribution": round(net, 3),
                "turnover_contribution": len(closed),
                "avg_holding_period_days": round(avg_hold, 3),
                "win_rate": round(len(wins) / len(closed), 6) if closed else 0.0,
                "profit_factor": round(profit_factor, 6) if closed else 0.0,
                "avg_tranches": round(avg_tranches, 3),
                "selected_strategy_mix": self._normalize_counter(Counter(row.get("selected_strategy", "unknown") for row in symbol_signal_rows)),
                "recommendation": recommendation,
                "repair_mode": repair_mode,
                "primary_blockers": [name for name, _ in blocker_counter.most_common(3)],
                "screening_pass_rate": round(screening_pass_count / len(symbol_signal_rows), 6) if symbol_signal_rows else 0.0,
                "actionable_signal_rate": round(len(actionable_signals) / len(symbol_signal_rows), 6) if symbol_signal_rows else 0.0,
                "trade_conversion_rate": round(len(closed) / len(actionable_signals), 6) if actionable_signals else 0.0,
                "hard_risk_exit_rate": round(hard_risk_exits / len(closed), 6) if closed else 0.0,
            }
        return recommendations
