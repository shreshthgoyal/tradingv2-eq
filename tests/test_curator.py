import unittest
from datetime import date

from tradingbot.core.models import (
    FundamentalSnapshot,
    MarketContext,
    PriceBar,
    ScreenerSnapshot,
    SymbolSnapshot,
)
from tradingbot.data_ingest.nse_market_curator.curator import MarketCurator


class FakeNseAdapter:
    def get_symbol_snapshot(self, symbol: str, trade_date: date) -> dict:
        return {
            "symbol": symbol,
            "price_bar": PriceBar(
                symbol=symbol,
                trade_date=trade_date,
                open=5000.0,
                high=5100.0,
                low=4950.0,
                close=5075.0,
                volume=100000,
                turnover=500000000.0,
                delivery_pct=42.0,
            ),
            "market_context": MarketContext(
                benchmark_symbol="NIFTY 50",
                benchmark_close=24000.0,
                sector_name="Defence",
                sector_index_close=12000.0,
                vix_close=16.0,
            ),
            "source_map": {"nselib": ["price_bar", "market_context"]},
        }


class FakeScreenerAdapter:
    def get_symbol_snapshot(self, symbol: str) -> ScreenerSnapshot:
        return ScreenerSnapshot(
            symbol=symbol,
            analysis_pros=["Strong order book"],
            analysis_cons=["Rich valuation"],
            shareholding={"Promoters": 71.0},
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
        )


class CuratorTest(unittest.TestCase):
    def test_curator_merges_nse_and_screener_data(self) -> None:
        curator = MarketCurator(FakeNseAdapter(), FakeScreenerAdapter())
        snapshot = curator.curate_symbol("HAL", date(2026, 5, 25))

        self.assertIsInstance(snapshot, SymbolSnapshot)
        self.assertEqual(snapshot.symbol, "HAL")
        self.assertEqual(snapshot.market_context.vix_close, 16.0)
        self.assertEqual(snapshot.fundamentals.promoter_holding, 71.0)
        self.assertIn("nselib", snapshot.source_map)
        self.assertIn("screener", snapshot.source_map)
