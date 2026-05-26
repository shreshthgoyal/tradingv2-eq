import unittest
from datetime import date

import pandas as pd

from tradingbot.core.models import ResearchDateRange
from tradingbot.data_ingest.nselib_adapter.adapter import NseLibAdapter, _to_float


class NseLibAdapterTest(unittest.TestCase):
    def test_to_float_handles_commas_and_currency_symbols(self) -> None:
        self.assertEqual(_to_float("4,352.50"), 4352.5)
        self.assertEqual(_to_float("1,23,456"), 123456.0)
        self.assertEqual(_to_float("10.5%"), 10.5)

    def test_adapter_caches_shared_network_calls_by_date_range(self) -> None:
        class StubCapitalMarket:
            def __init__(self) -> None:
                self.calls = {
                    "event_calendar_for_equity": 0,
                    "corporate_actions_for_equity": 0,
                    "india_vix_data": 0,
                    "index_data": 0,
                }

            def event_calendar_for_equity(self, **kwargs):
                self.calls["event_calendar_for_equity"] += 1
                return pd.DataFrame([
                    {"Symbol": "HAL", "Date": "01-01-2024", "purpose": "results"},
                    {"Symbol": "BEL", "Date": "02-01-2024", "purpose": "results"},
                ])

            def corporate_actions_for_equity(self, **kwargs):
                self.calls["corporate_actions_for_equity"] += 1
                return pd.DataFrame([
                    {"Symbol": "HAL", "Date": "01-01-2024", "purpose": "split"},
                    {"Symbol": "BEL", "Date": "02-01-2024", "purpose": "dividend"},
                ])

            def india_vix_data(self, **kwargs):
                self.calls["india_vix_data"] += 1
                return pd.DataFrame([{"TIMESTAMP": "01-Jan-2024", "CLOSE_INDEX_VAL": "14.5"}])

            def index_data(self, **kwargs):
                self.calls["index_data"] += 1
                return pd.DataFrame([
                    {
                        "TIMESTAMP": "01-Jan-2024",
                        "OPEN_INDEX_VAL": "100",
                        "HIGH_INDEX_VAL": "101",
                        "LOW_INDEX_VAL": "99",
                        "CLOSE_INDEX_VAL": "100.5",
                        "TRADED_QTY": "0",
                        "TURN_OVER": "0",
                    }
                ])

        adapter = NseLibAdapter.__new__(NseLibAdapter)
        adapter.capital_market = StubCapitalMarket()
        adapter._symbol_history_cache = {}
        adapter._benchmark_history_cache = {}
        adapter._vix_history_cache = {}
        adapter._event_calendar_frame_cache = {}
        adapter._corporate_actions_frame_cache = {}
        date_range = ResearchDateRange(date(2024, 1, 1), date(2024, 1, 31))

        adapter.get_event_calendar("HAL", date_range)
        adapter.get_event_calendar("BEL", date_range)
        adapter.get_corporate_actions("HAL", date_range)
        adapter.get_corporate_actions("BEL", date_range)
        adapter.get_vix_history(date_range)
        adapter.get_vix_history(date_range)
        adapter.get_benchmark_history("NIFTY 50", date_range)
        adapter.get_benchmark_history("NIFTY 50", date_range)

        self.assertEqual(adapter.capital_market.calls["event_calendar_for_equity"], 1)
        self.assertEqual(adapter.capital_market.calls["corporate_actions_for_equity"], 1)
        self.assertEqual(adapter.capital_market.calls["india_vix_data"], 1)
        self.assertEqual(adapter.capital_market.calls["index_data"], 1)
