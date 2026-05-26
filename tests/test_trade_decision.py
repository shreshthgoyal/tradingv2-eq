import json
import unittest
from datetime import date, datetime, timezone

from tradingbot.core.enums import DecisionStatus, DecisionType, Mode, RegimeLabel
from tradingbot.core.models import TradeDecision


class TradeDecisionTest(unittest.TestCase):
    def test_trade_decision_serializes_required_fields(self) -> None:
        decision = TradeDecision(
            decision_id="dec-1",
            run_id="run-1",
            strategy_version="v1",
            config_hash="cfg",
            mode=Mode.PAPER,
            decision=DecisionType.ENTER_LONG,
            decision_status=DecisionStatus.APPROVED,
            symbol="HAL",
            trade_date=date(2026, 5, 25),
            effective_session="NEXT_SESSION_OPEN",
            regime={"label": RegimeLabel.BULL_TRENDING.value, "confidence": 0.9, "factors": {}},
            screening={"investable": True, "passed_checks": ["LIQUIDITY_OK"], "failed_checks": [], "risk_flags": []},
            scores={"composite_score": 0.9, "entry_threshold": 0.55, "hold_threshold": 0.45},
            market_data={"close": 5075.0},
            fundamentals={"roce": 28.0},
            portfolio_context={"nav": 100000.0},
            risk_plan={"position_size_qty": 5, "initial_stop": 4800.0},
            execution_plan={"entry_style": "NEXT_OPEN_LIMIT", "exit_style": "STOP"},
            reason_codes=["REGIME_SUPPORTIVE"],
            human_reason="HAL passed all configured gates.",
            created_at_ist=datetime(2026, 5, 25, 12, 0, tzinfo=timezone.utc),
        )

        payload = decision.to_dict()
        self.assertEqual(payload["symbol"], "HAL")
        self.assertEqual(payload["mode"], "PAPER")
        self.assertEqual(payload["regime"]["label"], "BULL_TRENDING")
        json.dumps(payload)
