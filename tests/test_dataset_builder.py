from datetime import date
import unittest

from tradingbot.core.enums import PeriodType
from tradingbot.core.models import (
    FundamentalSnapshot,
    HistoricalFundamentalPoint,
    HistoricalPriceBar,
    HistoricalShareholdingPoint,
    ResearchDateRange,
)
from tradingbot.data_ingest.nse_market_curator.dataset_builder import ResearchDatasetBuilder
from tradingbot.data_ingest.screener_adapter.history_models import ScreenerHistoricalDataset


class FakeHistoricalNseAdapter:
    def get_symbol_history(self, symbol: str, date_range: ResearchDateRange):
        return [
            HistoricalPriceBar(symbol, date(2025, 1, 1), 100, 110, 95, 108, 1000, 1200000, 35.0),
            HistoricalPriceBar(symbol, date(2025, 1, 2), 108, 112, 100, 111, 1100, 1300000, 38.0),
        ]

    def get_benchmark_history(self, benchmark_symbol: str, date_range: ResearchDateRange):
        return [
            HistoricalPriceBar(benchmark_symbol, date(2025, 1, 1), 200, 205, 198, 203, 0, 0, 0),
            HistoricalPriceBar(benchmark_symbol, date(2025, 1, 2), 203, 208, 202, 207, 0, 0, 0),
        ]

    def get_vix_history(self, date_range: ResearchDateRange):
        return {
            date(2025, 1, 1): 14.0,
            date(2025, 1, 2): 15.0,
        }

    def get_event_calendar(self, symbol: str, date_range: ResearchDateRange):
        return {}

    def get_corporate_actions(self, symbol: str, date_range: ResearchDateRange):
        return {}


class FakeHistoricalScreenerAdapter:
    def get_symbol_history(self, symbol: str) -> ScreenerHistoricalDataset:
        return ScreenerHistoricalDataset(
            symbol=symbol,
            static_pros=["Healthy balance sheet"],
            static_cons=["Expensive"],
            static_metrics={"Compounded Sales Growth": {"1 Year": 12.0}},
            fundamental_points=[
                HistoricalFundamentalPoint(
                    symbol=symbol,
                    metric_name="roce",
                    value=28.0,
                    period_end=date(2024, 3, 31),
                    period_type=PeriodType.ANNUAL,
                    source_label="ratios",
                    availability_assumption="annual_report_plus_90d",
                    available_from=date(2024, 6, 29),
                )
            ],
            shareholding_points=[
                HistoricalShareholdingPoint(
                    symbol=symbol,
                    metric_name="Promoters",
                    value=72.0,
                    period_end=date(2024, 3, 31),
                    period_type=PeriodType.QUARTERLY,
                    source_label="shareholding",
                    availability_assumption="quarterly_result_plus_45d",
                    available_from=date(2024, 5, 15),
                )
            ],
            latest_snapshot=FundamentalSnapshot(
                sales_growth_yoy=12.0,
                profit_growth_yoy=14.0,
                operating_cashflow_trend=1.0,
                roce=28.0,
                roe=18.0,
                debt_to_equity=0.4,
                promoter_holding=72.0,
                promoter_pledge=0.0,
            ),
        )


class DatasetBuilderTest(unittest.TestCase):
    def test_dataset_builder_merges_histories_and_report(self) -> None:
        builder = ResearchDatasetBuilder(FakeHistoricalNseAdapter(), FakeHistoricalScreenerAdapter())
        dataset = builder.build("HAL", "NIFTY 50", ResearchDateRange(date(2025, 1, 1), date(2025, 1, 2)))

        self.assertEqual(dataset.symbol, "HAL")
        self.assertEqual(len(dataset.price_bars), 2)
        self.assertEqual(dataset.dataset_report.first_available_date, date(2025, 1, 1))
        self.assertEqual(dataset.dataset_report.last_available_date, date(2025, 1, 2))
        self.assertIn("static_cons", dataset.screener_history.__dict__)
