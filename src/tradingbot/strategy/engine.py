from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from uuid import uuid4

from tradingbot.core.enums import DecisionStatus, DecisionType, Mode
from tradingbot.core.models import RegimeState, SymbolSnapshot, TradeDecision
from tradingbot.indicators.calculator import IndicatorCalculator
from tradingbot.risk.position_sizer import PositionSizer
from tradingbot.screening.engine import ScreeningEngine


class StrategyEngine:
    def __init__(self) -> None:
        self.screening_engine = ScreeningEngine()
        self.indicator_calculator = IndicatorCalculator()
        self.position_sizer = PositionSizer()
        self.entry_threshold = 0.55
        self.hold_threshold = 0.45
        self.time_stop_bars = 20

    def evaluate(self, snapshot: SymbolSnapshot, regime: RegimeState, nav: float, cash: float) -> TradeDecision:
        screening = self.screening_engine.evaluate(snapshot)
        scores = self.indicator_calculator.score(snapshot, regime.label.value)
        scores["entry_threshold"] = self.entry_threshold
        scores["hold_threshold"] = self.hold_threshold
        risk_plan = self.position_sizer.size(snapshot.price_bar, nav, cash)
        approved = screening["investable"] and regime.label.value.startswith("BULL") and scores["composite_score"] >= self.entry_threshold and risk_plan["position_size_qty"] > 0
        decision = DecisionType.ENTER_LONG if approved else DecisionType.REJECTED
        status = DecisionStatus.APPROVED if approved else DecisionStatus.BLOCKED
        reason_codes = ["REGIME_SUPPORTIVE"] if approved else ["SCREENING_BLOCKED"]
        human_reason = (
            f"{snapshot.symbol} passed all configured gates."
            if approved
            else f"{snapshot.symbol} failed one or more screening or scoring gates."
        )
        return TradeDecision(
            decision_id=str(uuid4()),
            run_id="daily-run",
            strategy_version="v1",
            config_hash="local-dev",
            mode=Mode.PAPER,
            decision=decision,
            decision_status=status,
            symbol=snapshot.symbol,
            trade_date=snapshot.trade_date,
            effective_session="NEXT_SESSION_OPEN",
            regime={
                "label": regime.label.value,
                "confidence": regime.confidence,
                "factors": regime.factors,
            },
            screening=screening,
            scores=scores,
            market_data={
                "close": snapshot.price_bar.close,
                "open": snapshot.price_bar.open,
                "high": snapshot.price_bar.high,
                "low": snapshot.price_bar.low,
                "volume": snapshot.price_bar.volume,
                "turnover": snapshot.price_bar.turnover,
                "delivery_pct": snapshot.price_bar.delivery_pct,
            },
            fundamentals=asdict(snapshot.fundamentals),
            portfolio_context={
                "nav": nav,
                "cash_before": cash,
                "cash_after_expected": round(cash - risk_plan["position_size_notional"], 3),
            },
            risk_plan={
                **risk_plan,
                "risk_per_trade_pct": 0.01,
                "time_stop_bars": self.time_stop_bars,
            },
            execution_plan={
                "entry_style": "NEXT_OPEN_LIMIT",
                "exit_style": "STOP",
                "slippage_model_bps": 10.0,
                "impact_model_cost": 0.0,
                "fees_expected": 0.0,
            },
            reason_codes=reason_codes,
            human_reason=human_reason,
            created_at_ist=datetime.now(timezone.utc),
        )
