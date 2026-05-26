from __future__ import annotations

from datetime import timedelta

import pandas as pd

from tradingbot.core.enums import RegimeLabel, SignalState
from tradingbot.core.models import IndicatorSnapshot, ResearchDataset, SignalObservation


DEFAULT_CANDIDATES = {
    "franchise_pullback_accumulator": {
        "entry_style": "pullback",
        "trend_weight": 1.05,
        "pullback_weight": 1.2,
        "momentum_weight": 0.9,
        "fundamental_weight": 1.2,
        "liquidity_weight": 0.8,
        "regime_weight": 1.1,
        "seasonality_enabled": False,
        "event_drift_enabled": False,
        "risk_penalty_mult": 0.9,
        "entry_persistence": 3,
        "entry_quantile": 0.67,
        "hold_gap": 0.07,
        "add_threshold_boost": 0.05,
        "cooldown_days": 15,
        "fast_fail_days": 5,
        "fast_fail_cooldown_days": 30,
        "min_hold_days": 7,
        "min_hold_slack": 0.05,
        "min_long_trend_quality": 0.58,
        "min_relative_strength": 0.52,
        "min_pullback_quality": 0.60,
        "min_breakout_confirmation": 0.35,
        "add_persistence_boost": 2,
        "max_add_extension": 0.08,
        "partial_profit_trigger": 0.08,
        "max_tranches": 2,
    },
    "franchise_breakout_confirmed": {
        "entry_style": "breakout",
        "trend_weight": 1.1,
        "pullback_weight": 0.8,
        "momentum_weight": 1.2,
        "fundamental_weight": 1.15,
        "liquidity_weight": 0.9,
        "regime_weight": 1.15,
        "seasonality_enabled": False,
        "event_drift_enabled": False,
        "risk_penalty_mult": 1.0,
        "entry_persistence": 4,
        "entry_quantile": 0.72,
        "hold_gap": 0.06,
        "add_threshold_boost": 0.07,
        "cooldown_days": 20,
        "fast_fail_days": 5,
        "fast_fail_cooldown_days": 35,
        "min_hold_days": 9,
        "min_hold_slack": 0.05,
        "min_long_trend_quality": 0.66,
        "min_relative_strength": 0.58,
        "min_pullback_quality": 0.35,
        "min_breakout_confirmation": 0.62,
        "add_persistence_boost": 3,
        "max_add_extension": 0.05,
        "partial_profit_trigger": 0.10,
        "max_tranches": 2,
    },
    "franchise_risk_managed": {
        "entry_style": "pullback",
        "trend_weight": 1.0,
        "pullback_weight": 1.0,
        "momentum_weight": 0.85,
        "fundamental_weight": 1.25,
        "liquidity_weight": 0.9,
        "regime_weight": 1.2,
        "seasonality_enabled": False,
        "event_drift_enabled": False,
        "risk_penalty_mult": 1.35,
        "entry_persistence": 4,
        "entry_quantile": 0.70,
        "hold_gap": 0.05,
        "add_threshold_boost": 0.06,
        "cooldown_days": 20,
        "fast_fail_days": 5,
        "fast_fail_cooldown_days": 35,
        "min_hold_days": 8,
        "min_hold_slack": 0.04,
        "min_long_trend_quality": 0.64,
        "min_relative_strength": 0.55,
        "min_pullback_quality": 0.56,
        "min_breakout_confirmation": 0.40,
        "add_persistence_boost": 2,
        "max_add_extension": 0.06,
        "partial_profit_trigger": 0.08,
        "max_tranches": 2,
    },
    "franchise_event_drift": {
        "entry_style": "breakout",
        "trend_weight": 1.0,
        "pullback_weight": 1.0,
        "momentum_weight": 0.95,
        "fundamental_weight": 1.2,
        "liquidity_weight": 0.8,
        "regime_weight": 1.1,
        "seasonality_enabled": False,
        "event_drift_enabled": True,
        "risk_penalty_mult": 1.0,
        "entry_persistence": 3,
        "entry_quantile": 0.69,
        "hold_gap": 0.06,
        "add_threshold_boost": 0.05,
        "cooldown_days": 15,
        "fast_fail_days": 5,
        "fast_fail_cooldown_days": 30,
        "min_hold_days": 7,
        "min_hold_slack": 0.04,
        "min_long_trend_quality": 0.62,
        "min_relative_strength": 0.55,
        "min_pullback_quality": 0.40,
        "min_breakout_confirmation": 0.54,
        "add_persistence_boost": 2,
        "max_add_extension": 0.06,
        "partial_profit_trigger": 0.08,
        "max_tranches": 2,
    },
    "franchise_seasonality_enabled": {
        "entry_style": "pullback",
        "trend_weight": 1.0,
        "pullback_weight": 1.05,
        "momentum_weight": 0.9,
        "fundamental_weight": 1.2,
        "liquidity_weight": 0.8,
        "regime_weight": 1.0,
        "seasonality_enabled": True,
        "event_drift_enabled": False,
        "risk_penalty_mult": 1.0,
        "entry_persistence": 3,
        "entry_quantile": 0.66,
        "hold_gap": 0.07,
        "add_threshold_boost": 0.05,
        "cooldown_days": 15,
        "fast_fail_days": 5,
        "fast_fail_cooldown_days": 30,
        "min_hold_days": 7,
        "min_hold_slack": 0.04,
        "min_long_trend_quality": 0.58,
        "min_relative_strength": 0.50,
        "min_pullback_quality": 0.58,
        "min_breakout_confirmation": 0.38,
        "add_persistence_boost": 2,
        "max_add_extension": 0.08,
        "partial_profit_trigger": 0.08,
        "max_tranches": 2,
    },
}


class MasterStrategyEngine:
    def __init__(self, entry_threshold_floor: float, hold_threshold_floor: float) -> None:
        self.entry_threshold_floor = entry_threshold_floor
        self.hold_threshold_floor = hold_threshold_floor

    def _symbol_profile(self, symbol_profile: dict | None, symbol_tags: list[str] | None) -> dict:
        profile = dict(symbol_profile or {})
        profile.setdefault("tags", list(symbol_tags or profile.get("tags", []) or []))
        profile.setdefault("screening", {})
        profile.setdefault("strategy", {})
        return profile

    def _screening_thresholds(self, profile: dict) -> dict[str, float]:
        screening = profile.get("screening", {})
        return {
            "min_turnover_ma_20": float(screening.get("min_turnover_ma_20", 100000000.0)),
            "min_delivery_ratio": float(screening.get("min_delivery_ratio", 25.0)),
            "max_realized_vol_20d": float(screening.get("max_realized_vol_20d", 0.80)),
            "max_gap_risk": float(screening.get("max_gap_risk", 0.15)),
        }

    def _merged_candidate(self, candidate: dict, profile: dict) -> dict:
        merged = dict(candidate)
        strategy_overrides = profile.get("strategy", {})
        merged["entry_persistence"] = int(strategy_overrides.get("entry_persistence", merged["entry_persistence"]))
        merged["entry_score_offset"] = float(strategy_overrides.get("entry_score_offset", 0.0))
        merged["hold_score_offset"] = float(strategy_overrides.get("hold_score_offset", 0.0))
        merged["min_breakout_confirmation"] = float(strategy_overrides.get("min_breakout_confirmation", merged["min_breakout_confirmation"]))
        merged["min_pullback_quality"] = float(strategy_overrides.get("min_pullback_quality", merged["min_pullback_quality"]))
        merged["min_relative_strength"] = float(strategy_overrides.get("min_relative_strength", merged["min_relative_strength"]))
        merged["min_long_trend_quality"] = float(strategy_overrides.get("min_long_trend_quality", merged["min_long_trend_quality"]))
        merged["cooldown_days"] = int(strategy_overrides.get("cooldown_days", merged["cooldown_days"]))
        merged["fast_fail_cooldown_days"] = int(strategy_overrides.get("fast_fail_cooldown_days", merged["fast_fail_cooldown_days"]))
        merged["min_hold_days"] = int(strategy_overrides.get("min_hold_days", merged["min_hold_days"]))
        merged["atr_stop_multiplier"] = float(strategy_overrides.get("atr_stop_multiplier", 0.0))
        return merged

    def evaluate(self, dataset: ResearchDataset, indicators, regimes, screenings, train_years: int, test_years: int) -> list[SignalObservation]:
        regime_map = {item.trade_date: item for item in regimes}
        screening_map = {item.trade_date: item for item in screenings}
        raw_scores = []
        for indicator in indicators:
            regime = regime_map.get(indicator.trade_date)
            screening = screening_map.get(indicator.trade_date)
            raw_scores.append(self._raw_signal_row(dataset, indicator, regime, screening))

        windows = self._build_windows([row["trade_date"] for row in raw_scores], train_years=train_years, test_years=test_years)
        thresholds_by_date: dict = {}
        for train_dates, test_dates in windows:
            training_scores = [
                row["composite_score"]
                for row in raw_scores
                if row["trade_date"] in train_dates and row["screening_investable"]
            ]
            calibrated_entry = self.entry_threshold_floor
            if training_scores:
                calibrated_entry = max(self.entry_threshold_floor, float(pd.Series(training_scores).quantile(0.60)))
            calibrated_hold = max(self.hold_threshold_floor, calibrated_entry - 0.08)
            for trade_date in test_dates:
                thresholds_by_date[trade_date] = (round(calibrated_entry, 3), round(calibrated_hold, 3))
        if not thresholds_by_date:
            for row in raw_scores:
                thresholds_by_date[row["trade_date"]] = (self.entry_threshold_floor, self.hold_threshold_floor)

        signals: list[SignalObservation] = []
        for row in raw_scores:
            entry_threshold, hold_threshold = thresholds_by_date.get(
                row["trade_date"],
                (self.entry_threshold_floor, self.hold_threshold_floor),
            )
            if row["screening_investable"] and row["regime_supportive"] and row["composite_score"] >= entry_threshold:
                state = SignalState.ENTER
                reasons = ["REGIME_SUPPORTIVE", "SCREENING_PASSED", "SCORE_ABOVE_ENTRY"]
                threshold = entry_threshold
            elif row["screening_investable"] and row["regime_supportive"] and row["composite_score"] >= hold_threshold:
                state = SignalState.HOLD
                reasons = ["REGIME_SUPPORTIVE", "SCREENING_PASSED", "SCORE_ABOVE_HOLD"]
                threshold = hold_threshold
            elif row["screening_investable"]:
                state = SignalState.EXIT
                reasons = ["SCORE_BELOW_HOLD"]
                threshold = hold_threshold
            else:
                state = SignalState.REJECT
                reasons = row["screening_failures"] or ["SCREENING_BLOCKED"]
                threshold = entry_threshold
            signals.append(
                SignalObservation(
                    symbol=dataset.symbol,
                    trade_date=row["trade_date"],
                    state=state.value,
                    module_scores=row["module_scores"],
                    composite_score=row["composite_score"],
                    threshold=threshold,
                    reasons=reasons,
                )
            )
        return signals

    def evaluate_candidates(
        self,
        dataset: ResearchDataset,
        indicators,
        regimes,
        screenings,
        train_years: int,
        test_years: int,
        candidate_set: str = "default",
        symbol_profile: dict | None = None,
        symbol_tags: list[str] | None = None,
    ) -> dict[str, list[SignalObservation]]:
        candidates = DEFAULT_CANDIDATES if candidate_set == "default" else DEFAULT_CANDIDATES
        profile = self._symbol_profile(symbol_profile, symbol_tags)
        return {
            name: self._evaluate_with_candidate(dataset, indicators, regimes, screenings, train_years, test_years, params, profile)
            for name, params in candidates.items()
        }

    def _evaluate_with_candidate(self, dataset: ResearchDataset, indicators, regimes, screenings, train_years: int, test_years: int, candidate: dict, symbol_profile: dict) -> list[SignalObservation]:
        candidate = self._merged_candidate(candidate, symbol_profile)
        regime_map = {item.trade_date: item for item in regimes}
        screening_map = {item.trade_date: item for item in screenings}
        raw_scores = []
        for indicator in indicators:
            regime = regime_map.get(indicator.trade_date)
            screening = screening_map.get(indicator.trade_date)
            raw_scores.append(self._raw_signal_row(dataset, indicator, regime, screening, candidate, symbol_profile))

        windows = self._build_windows([row["trade_date"] for row in raw_scores], train_years=train_years, test_years=test_years)
        thresholds_by_date: dict = {}
        for train_dates, test_dates in windows:
            training_scores = [row["composite_score"] for row in raw_scores if row["trade_date"] in train_dates and row["screening_investable"]]
            calibrated_entry = self.entry_threshold_floor
            if training_scores:
                quantile = candidate.get("entry_quantile", 0.65 if candidate["risk_penalty_mult"] > 1.0 else 0.60)
                calibrated_entry = max(self.entry_threshold_floor, float(pd.Series(training_scores).quantile(quantile)))
            calibrated_hold = max(self.hold_threshold_floor, calibrated_entry - candidate.get("hold_gap", 0.08))
            for trade_date in test_dates:
                thresholds_by_date[trade_date] = (round(calibrated_entry, 3), round(calibrated_hold, 3))
        if not thresholds_by_date:
            for row in raw_scores:
                thresholds_by_date[row["trade_date"]] = (self.entry_threshold_floor, self.hold_threshold_floor)

        signals: list[SignalObservation] = []
        supportive_streak = 0
        conviction_streak = 0
        in_position = False
        tranche_count = 0
        last_exit_date = None
        cooldown_until = None
        entry_start_date = None
        for row in raw_scores:
            entry_threshold, hold_threshold = thresholds_by_date.get(row["trade_date"], (self.entry_threshold_floor, self.hold_threshold_floor))
            entry_threshold = round(
                entry_threshold
                + candidate.get("entry_score_offset", 0.0)
                + row.get("soft_threshold_bump", 0.0)
                + row.get("regime_threshold_bump", 0.0),
                3,
            )
            hold_threshold = round(hold_threshold + candidate.get("hold_score_offset", 0.0), 3)
            supportive = row["screening_pass"] and row["regime_state"] != "hard_block" and row["composite_score"] >= hold_threshold
            conviction = supportive and row["entry_quality_ok"] and row["composite_score"] >= entry_threshold
            supportive_streak = supportive_streak + 1 if supportive else 0
            conviction_streak = conviction_streak + 1 if conviction else 0
            cooldown_active = bool(cooldown_until and row["trade_date"] < cooldown_until)
            holding_days = max((row["trade_date"] - entry_start_date).days, 0) if in_position and entry_start_date else 0
            threshold = hold_threshold
            score_margin = round(row["composite_score"] - entry_threshold, 6)
            entry_band = "reject"
            entry_blockers = list(row["screening_blockers"])
            if not row["screening_pass"]:
                if in_position:
                    state = SignalState.EXIT_FULL
                    reasons = row["screening_blockers"] or ["SCREENING_BLOCKED"]
                    in_position = False
                    tranche_count = 0
                    last_exit_date = row["trade_date"]
                    cooldown_until = row["trade_date"] + timedelta(days=candidate["cooldown_days"])
                    entry_start_date = None
                else:
                    state = SignalState.REJECT
                    reasons = row["screening_blockers"] or ["SCREENING_BLOCKED"]
                    threshold = entry_threshold
            elif row["regime_state"] == "hard_block":
                if in_position:
                    state = SignalState.REDUCE_PARTIAL if tranche_count > 1 else SignalState.EXIT_FULL
                    reasons = ["REGIME_NOT_SUPPORTIVE"]
                    tranche_count = max(tranche_count - 1, 0) if state == SignalState.REDUCE_PARTIAL else 0
                    in_position = tranche_count > 0
                    if not in_position:
                        last_exit_date = row["trade_date"]
                        cooldown_until = row["trade_date"] + timedelta(days=candidate["cooldown_days"])
                        entry_start_date = None
                else:
                    state = SignalState.REJECT
                    reasons = ["REGIME_NOT_SUPPORTIVE"]
                    threshold = entry_threshold
                    entry_blockers = ["REGIME_NOT_SUPPORTIVE"]
            elif (
                not in_position
                and not cooldown_active
                and row["regime_state"] == "fully_supportive"
                and conviction_streak >= candidate["entry_persistence"]
                and row["composite_score"] >= entry_threshold
            ):
                state = SignalState.ENTER_PARTIAL
                reasons = ["REGIME_SUPPORTIVE", "SCREENING_PASSED", "SCORE_ABOVE_ENTRY", "HIGH_CONVICTION_ENTRY", "TREND_QUALITY_CONFIRMED"]
                if row["regime_state"] == "soft_penalty":
                    reasons.append("REGIME_SOFT_PENALTY")
                threshold = entry_threshold
                in_position = True
                tranche_count = 1
                entry_start_date = row["trade_date"]
                entry_band = "high_conviction_entry"
            elif in_position and tranche_count < candidate["max_tranches"] and conviction_streak >= candidate["entry_persistence"] + candidate["add_persistence_boost"] and row["composite_score"] >= entry_threshold + candidate["add_threshold_boost"] and row["add_quality_ok"] and not row["extended_for_add"]:
                state = SignalState.ADD_PARTIAL
                reasons = ["REGIME_SUPPORTIVE", "THESIS_CONFIRMED", "ADD_THRESHOLD_CLEARED"]
                reasons.append("PULLBACK_ACCUMULATION" if candidate["entry_style"] == "pullback" else "BREAKOUT_CONFIRMED")
                threshold = entry_threshold + candidate["add_threshold_boost"]
                tranche_count += 1
                entry_band = "high_conviction_entry"
            elif (
                not in_position
                and not cooldown_active
                and supportive_streak >= max(2, candidate["entry_persistence"] - 1)
                and row["entry_quality_ok"]
                and (
                    0.0 <= score_margin < 0.025
                    or (row["regime_state"] == "soft_penalty" and 0.0 <= score_margin < 0.30)
                )
            ):
                state = SignalState.ENTER_PARTIAL
                reasons = ["REGIME_SUPPORTIVE", "SCREENING_PASSED", "STANDARD_ENTRY", "SCORE_NEAR_ENTRY"]
                if row["regime_state"] == "soft_penalty":
                    reasons.append("REGIME_SOFT_PENALTY")
                threshold = entry_threshold
                in_position = True
                tranche_count = 1
                entry_start_date = row["trade_date"]
                entry_band = "standard_entry"
            elif in_position and row["composite_score"] < hold_threshold:
                if holding_days < candidate["min_hold_days"] and row["hold_quality_ok"]:
                    state = SignalState.HOLD
                    reasons = ["MIN_HOLD_ACTIVE", "TREND_OWNERSHIP", "EARLY_WEAKNESS_TOLERATED"]
                    entry_band = "watchlist_hold"
                else:
                    state = SignalState.REDUCE_PARTIAL if tranche_count > 1 else SignalState.EXIT_FULL
                    reasons = ["SCORE_BELOW_HOLD"]
                    threshold = hold_threshold
                    tranche_count = max(tranche_count - 1, 0) if state == SignalState.REDUCE_PARTIAL else 0
                    in_position = tranche_count > 0
                    if not in_position:
                        last_exit_date = row["trade_date"]
                        cooldown_days = candidate["fast_fail_cooldown_days"] if holding_days <= candidate["fast_fail_days"] else candidate["cooldown_days"]
                        cooldown_until = row["trade_date"] + timedelta(days=cooldown_days)
                        entry_start_date = None
            elif in_position and tranche_count > 1 and holding_days >= candidate["min_hold_days"] and row["partial_profit_ready"]:
                state = SignalState.REDUCE_PARTIAL
                reasons = ["PROFIT_LOCK", "PARTIAL_DE_RISK", "TREND_OWNERSHIP"]
                tranche_count -= 1
            elif in_position:
                state = SignalState.HOLD
                reasons = ["TREND_OWNERSHIP", "SCREENING_PASSED", "SCORE_ABOVE_HOLD"]
                entry_band = "watchlist_hold"
            else:
                state = SignalState.REJECT
                if cooldown_active:
                    reasons = ["REENTRY_COOLDOWN_ACTIVE"]
                    entry_blockers = ["REENTRY_COOLDOWN_ACTIVE"]
                elif conviction_streak < candidate["entry_persistence"]:
                    reasons = ["AWAITING_PERSISTENCE"]
                    entry_band = "watchlist_hold"
                elif not row["entry_quality_ok"] and supportive:
                    reasons = ["ENTRY_QUALITY_NOT_CONFIRMED"]
                    entry_band = "watchlist_hold"
                    entry_blockers = ["ENTRY_QUALITY_NOT_CONFIRMED"]
                else:
                    reasons = ["ENTRY_THRESHOLD_NOT_MET"]
                    entry_blockers = ["ENTRY_THRESHOLD_NOT_MET"]
                threshold = entry_threshold
            if candidate["seasonality_enabled"] and row["module_scores"]["seasonality"] > 0 and state in {SignalState.ENTER_PARTIAL, SignalState.ADD_PARTIAL}:
                reasons.append("SEASONALITY_SUPPORTIVE")
            if candidate["event_drift_enabled"] and row["module_scores"]["event_drift"] > 0 and state in {SignalState.ENTER_PARTIAL, SignalState.ADD_PARTIAL}:
                reasons.append("EVENT_DRIFT_SUPPORTIVE")
            signals.append(
                SignalObservation(
                    symbol=dataset.symbol,
                    trade_date=row["trade_date"],
                    state=state.value,
                    module_scores=row["module_scores"],
                    composite_score=row["composite_score"],
                    threshold=threshold,
                    reasons=reasons,
                    screening_pass=row["screening_pass"],
                    screening_blockers=list(row["screening_blockers"]),
                    soft_blockers=list(row["soft_blockers"]),
                    regime_state=row["regime_state"],
                    entry_band=entry_band,
                    entry_blockers=entry_blockers,
                    score_margin=score_margin,
                    screening_details=row["screening_details"],
                )
            )
        return signals

    def _raw_signal_row(self, dataset: ResearchDataset, indicator: IndicatorSnapshot, regime, screening, candidate: dict | None = None, symbol_profile: dict | None = None) -> dict:
        candidate = candidate or DEFAULT_CANDIDATES["franchise_pullback_accumulator"]
        profile = self._symbol_profile(symbol_profile, None)
        symbol_tags = profile.get("tags", [])
        screening_thresholds = self._screening_thresholds(profile)
        fundamentals = dataset.screener_history.latest_snapshot
        values = indicator.values
        trend_score = min(max((values.get("returns_63d", 0.0) + 0.12) / 0.24, 0.0), 1.0)
        relative_strength = min(max((values.get("relative_strength_63d", 0.0) + 0.05) / 0.10, 0.0), 1.0)
        sma50_support = min(max((values.get("distance_to_sma_50", 0.0) + 0.02) / 0.10, 0.0), 1.0)
        sma200_support = min(max((values.get("distance_to_sma_200", 0.0) + 0.03) / 0.15, 0.0), 1.0)
        long_trend_quality = round((trend_score + relative_strength + sma50_support + sma200_support) / 4.0, 3)
        pullback_depth_fit = 1.0 - min(abs(values.get("pullback_zscore", 0.0) + 0.6) / 2.2, 1.0)
        pullback_score = round((pullback_depth_fit + long_trend_quality + relative_strength) / 3.0, 3)
        momentum_quality = min(max((values.get("returns_20d", 0.0) + 0.10) / 0.20, 0.0), 1.0)
        breakout_distance_score = min(max(values.get("breakout_distance", 0.0) / 0.06, 0.0), 1.0)
        breakout_confirmation = round((breakout_distance_score + momentum_quality + relative_strength + sma50_support) / 4.0, 3)
        mean_reversion_veto = 0.20 if values.get("distance_to_sma_20", 0.0) > 0.10 else 0.0
        fundamental_quality = min(max((fundamentals.roce + fundamentals.roe) / 60.0, 0.0), 1.0)
        liquidity_gate = min(max(values.get("turnover_ma_20", 0.0) / 500000000.0, 0.0), 1.0)
        if regime and regime.label == RegimeLabel.BULL_TRENDING:
            regime_gate = 1.0
        elif regime and regime.label == RegimeLabel.BULL_RANGING:
            regime_gate = 0.78
        elif regime and regime.label == RegimeLabel.BEAR_RANGING:
            regime_gate = 0.58
        else:
            regime_gate = 0.2
        event_gate = 0.0 if screening and "EVENT_BLACKOUT" in screening.failed_checks else 1.0
        ownership_bias = round((fundamental_quality + long_trend_quality + regime_gate) / 3.0, 3)
        dominant_bonus = 0.12 if "dominant_franchise" in symbol_tags else 0.0
        lower_priority_penalty = 0.10 if "lower_priority" in symbol_tags else 0.0
        cyclical_penalty = 0.05 if "commodity_cyclical" in symbol_tags else 0.0
        event_risk_penalty = 0.04 if "event_heavy" in symbol_tags and not candidate["event_drift_enabled"] else 0.0
        seasonality_score = (
            0.5 * values.get("seasonality_turn_of_month", 0.0) + 0.3 * values.get("seasonality_month_of_year", 0.0)
            if candidate["seasonality_enabled"]
            else 0.0
        )
        event_drift_score = values.get("event_drift_score", 0.0) if candidate["event_drift_enabled"] else 0.0
        risk_penalty = (0.15 if values.get("realized_vol_20d", 0.0) > 0.6 else 0.05) * candidate["risk_penalty_mult"]
        trend_component = round((trend_score + long_trend_quality + relative_strength) / 3.0, 3)
        momentum_component = round((momentum_quality + breakout_confirmation) / 2.0, 3)
        composite = round(
            (
                trend_component * candidate["trend_weight"]
                + pullback_score * candidate["pullback_weight"]
                + momentum_component * candidate["momentum_weight"]
                + fundamental_quality * candidate["fundamental_weight"]
                + liquidity_gate * candidate["liquidity_weight"]
                + regime_gate * candidate["regime_weight"]
                + event_gate
                + seasonality_score
                + event_drift_score
                + dominant_bonus
                + ownership_bias * 0.25
            )
            / (
                candidate["trend_weight"]
                + candidate["pullback_weight"]
                + candidate["momentum_weight"]
                + candidate["fundamental_weight"]
                + candidate["liquidity_weight"]
                + candidate["regime_weight"]
                + 1.0
                + (1.0 if candidate["seasonality_enabled"] else 0.0)
                + (1.0 if candidate["event_drift_enabled"] else 0.0)
                + 0.25
            )
            - mean_reversion_veto
            - risk_penalty,
            3,
        )
        composite = round(composite - lower_priority_penalty - cyclical_penalty - event_risk_penalty, 3)
        entry_quality_ok = (
            long_trend_quality >= candidate["min_long_trend_quality"]
            and relative_strength >= candidate["min_relative_strength"]
            and (
                breakout_confirmation >= candidate["min_breakout_confirmation"]
                if candidate["entry_style"] == "breakout"
                else pullback_score >= candidate["min_pullback_quality"]
            )
        )
        add_quality_ok = (
            entry_quality_ok
            and values.get("distance_to_sma_20", 0.0) <= candidate["max_add_extension"]
            and (
                breakout_confirmation >= candidate["min_breakout_confirmation"] + 0.05
                if candidate["entry_style"] == "breakout"
                else pullback_score >= candidate["min_pullback_quality"] + 0.04
            )
        )
        hold_quality_ok = (
            long_trend_quality >= max(candidate["min_long_trend_quality"] - 0.12, 0.0)
            and relative_strength >= max(candidate["min_relative_strength"] - 0.10, 0.0)
            and composite >= self.hold_threshold_floor - candidate["min_hold_slack"]
        )
        partial_profit_ready = (
            ownership_bias >= 0.65
            and composite >= self.hold_threshold_floor + candidate["partial_profit_trigger"]
            and breakout_confirmation < long_trend_quality - 0.05
        )
        hard_blockers: list[str] = []
        soft_blockers: list[str] = []
        regime_state = "hard_block"
        regime_threshold_bump = 0.0
        blocker_classification = {
            "LIQUIDITY_LOW": "soft",
            "DELIVERY_LOW": "soft",
            "VOLATILITY_EXTREME": "soft",
            "GAP_RISK_HIGH": "soft",
            "FUNDAMENTAL_FLOOR_WEAK": "soft",
            "RELATIVE_STRENGTH_WEAK": "soft",
            "EVENT_BLACKOUT": "hard",
            "PROMOTER_PLEDGE_HIGH": "hard",
            "REGIME_UNSUITABLE": "hard",
        }
        for failure in (screening.failed_checks if screening else []):
            if blocker_classification.get(failure) == "hard":
                if failure not in hard_blockers:
                    hard_blockers.append(failure)
            elif failure not in soft_blockers:
                soft_blockers.append(failure)
        turnover_ok = values.get("turnover_ma_20", 0.0) >= screening_thresholds["min_turnover_ma_20"]
        delivery_ok = values.get("delivery_ma_20", 0.0) >= screening_thresholds["min_delivery_ratio"]
        vol_ok = 0.0 < values.get("realized_vol_20d", 0.0) <= screening_thresholds["max_realized_vol_20d"]
        gap_ok = abs(values.get("distance_to_sma_20", 0.0)) <= screening_thresholds["max_gap_risk"]
        if not turnover_ok and "LIQUIDITY_LOW" not in soft_blockers:
            soft_blockers.append("LIQUIDITY_LOW")
        if not delivery_ok and "DELIVERY_LOW" not in soft_blockers:
            soft_blockers.append("DELIVERY_LOW")
        if not vol_ok and "VOLATILITY_EXTREME" not in soft_blockers:
            soft_blockers.append("VOLATILITY_EXTREME")
        if not gap_ok and "GAP_RISK_HIGH" not in soft_blockers:
            soft_blockers.append("GAP_RISK_HIGH")
        if regime:
            if regime.label == RegimeLabel.BULL_TRENDING:
                regime_state = "fully_supportive"
            elif regime.label == RegimeLabel.BULL_RANGING:
                regime_state = "soft_penalty"
                regime_threshold_bump = 0.01
            elif regime.label == RegimeLabel.BEAR_RANGING and regime.confidence >= 0.55:
                regime_state = "soft_penalty"
                regime_threshold_bump = 0.02
            else:
                regime_state = "hard_block"
        if regime_state == "hard_block":
            if "REGIME_UNSUITABLE" not in hard_blockers:
                hard_blockers.append("REGIME_UNSUITABLE")
        elif "REGIME_UNSUITABLE" in hard_blockers:
            hard_blockers = [failure for failure in hard_blockers if failure != "REGIME_UNSUITABLE"]
            if "REGIME_UNSUITABLE" not in soft_blockers:
                soft_blockers.append("REGIME_UNSUITABLE")
        screening_pass = len(hard_blockers) == 0
        screening_failures = hard_blockers + [item for item in soft_blockers if item not in hard_blockers]
        soft_threshold_bump = round(0.01 * len(soft_blockers), 3)
        module_scores = {
            "trend": round(trend_component, 3),
            "pullback": round(pullback_score, 3),
            "momentum_quality": round(momentum_component, 3),
            "mean_reversion_veto": round(mean_reversion_veto, 3),
            "fundamental_quality": round(fundamental_quality, 3),
            "regime_gate": round(regime_gate, 3),
            "liquidity_gate": round(liquidity_gate, 3),
            "event_gate": round(event_gate, 3),
            "seasonality": round(seasonality_score, 3),
            "event_drift": round(event_drift_score, 3),
            "risk_penalty": round(risk_penalty, 3),
            "dominant_bonus": round(dominant_bonus, 3),
            "lower_priority_penalty": round(lower_priority_penalty + cyclical_penalty + event_risk_penalty, 3),
            "long_trend_quality": round(long_trend_quality, 3),
            "relative_strength": round(relative_strength, 3),
            "breakout_confirmation": round(breakout_confirmation, 3),
            "ownership_bias": round(ownership_bias, 3),
        }
        return {
            "trade_date": indicator.trade_date,
            "composite_score": composite,
            "module_scores": module_scores,
            "entry_quality_ok": entry_quality_ok,
            "add_quality_ok": add_quality_ok,
            "hold_quality_ok": hold_quality_ok,
            "partial_profit_ready": partial_profit_ready,
            "extended_for_add": values.get("distance_to_sma_20", 0.0) > candidate["max_add_extension"],
            "regime_supportive": regime_state != "hard_block",
            "regime_state": regime_state,
            "regime_threshold_bump": regime_threshold_bump,
            "screening_investable": bool(screening and screening.investable),
            "screening_pass": screening_pass,
            "screening_blockers": hard_blockers,
            "soft_blockers": soft_blockers,
            "soft_threshold_bump": soft_threshold_bump,
            "screening_failures": screening_failures,
            "screening_details": {
                "atr_14": float(values.get("atr_14", 0.0)),
                "turnover_ma_20": float(values.get("turnover_ma_20", 0.0)),
                "delivery_ma_20": float(values.get("delivery_ma_20", 0.0)),
                "realized_vol_20d": float(values.get("realized_vol_20d", 0.0)),
                "distance_to_sma_20": float(values.get("distance_to_sma_20", 0.0)),
                "min_turnover_ma_20": screening_thresholds["min_turnover_ma_20"],
                "min_delivery_ratio": screening_thresholds["min_delivery_ratio"],
                "max_realized_vol_20d": screening_thresholds["max_realized_vol_20d"],
                "max_gap_risk": screening_thresholds["max_gap_risk"],
            },
        }

    def _build_windows(self, trade_dates, train_years: int, test_years: int):
        years = sorted({trade_date.year for trade_date in trade_dates})
        windows = []
        cursor = train_years
        while cursor < len(years):
            train_set = set(years[max(0, cursor - train_years):cursor])
            test_set = set(years[cursor:cursor + test_years])
            train_dates = {trade_date for trade_date in trade_dates if trade_date.year in train_set}
            test_dates = {trade_date for trade_date in trade_dates if trade_date.year in test_set}
            if train_dates and test_dates:
                windows.append((train_dates, test_dates))
            cursor += test_years
        return windows
