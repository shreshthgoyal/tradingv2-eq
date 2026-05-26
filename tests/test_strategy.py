import unittest
from datetime import date

from tradingbot.core.enums import DecisionStatus, DecisionType, RegimeLabel
from tradingbot.core.models import (
    FundamentalSnapshot,
    MarketContext,
    PriceBar,
    RegimeState,
    SymbolSnapshot,
)
from tradingbot.strategy.engine import StrategyEngine


class StrategyTest(unittest.TestCase):
    def test_strategy_generates_entry_decision_with_reasoning(self) -> None:
        engine = StrategyEngine()
        snapshot = SymbolSnapshot(
            symbol="HAL",
            trade_date=date(2026, 5, 25),
            price_bar=PriceBar(
                symbol="HAL",
                trade_date=date(2026, 5, 25),
                open=5000.0,
                high=5100.0,
                low=4950.0,
                close=5075.0,
                volume=100000,
                turnover=500000000.0,
                delivery_pct=42.0,
            ),
            market_context=MarketContext(
                benchmark_symbol="NIFTY 50",
                benchmark_close=24000.0,
                sector_name="Defence",
                sector_index_close=12000.0,
                vix_close=16.0,
            ),
            fundamentals=FundamentalSnapshot(
                sales_growth_yoy=12.0,
                profit_growth_yoy=14.0,
                operating_cashflow_trend=1.0,
                roce=28.0,
                roe=24.0,
                debt_to_equity=0.1,
                promoter_holding=71.0,
                promoter_pledge=0.0,
            ),
            source_map={"nselib": ["price_bar"], "screener": ["fundamentals"]},
        )
        regime = RegimeState(
            label=RegimeLabel.BULL_TRENDING,
            confidence=0.8,
            factors={
                "benchmark_trend": 0.8,
                "breadth": 0.7,
                "volatility": 0.7,
                "sector_strength": 0.6,
                "flow_state": 0.5,
            },
        )

        decision = engine.evaluate(snapshot, regime, nav=100000.0, cash=100000.0)

        self.assertEqual(decision.decision, DecisionType.ENTER_LONG)
        self.assertEqual(decision.decision_status, DecisionStatus.APPROVED)
        self.assertTrue(decision.screening["investable"])
        self.assertIn("REGIME_SUPPORTIVE", decision.reason_codes)
