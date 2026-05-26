from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from itertools import groupby

from tradingbot.core.models import HistoricalPriceBar, ResearchDataset, ResearchDateRange


@dataclass
class DatasetQualityReport:
    symbol: str
    first_available_date: date | None
    last_available_date: date | None
    missing_ranges: list[tuple[date, date]]
    unavailable_factor_families: list[str]
    assumptions_applied: list[str]
    degraded_fields: list[str]


class ResearchDatasetBuilder:
    def __init__(self, nse_adapter, screener_adapter) -> None:
        self.nse_adapter = nse_adapter
        self.screener_adapter = screener_adapter

    def build(self, symbol: str, benchmark_symbol: str, date_range: ResearchDateRange) -> ResearchDataset:
        price_bars = sorted(
            self.nse_adapter.get_symbol_history(symbol, date_range),
            key=lambda item: item.trade_date,
        )
        benchmark_bars = sorted(
            self.nse_adapter.get_benchmark_history(benchmark_symbol, date_range),
            key=lambda item: item.trade_date,
        )
        vix_history = self.nse_adapter.get_vix_history(date_range)
        event_calendar = self.nse_adapter.get_event_calendar(symbol, date_range)
        corporate_actions = self.nse_adapter.get_corporate_actions(symbol, date_range)
        screener_history = self.screener_adapter.get_symbol_history(symbol)
        dataset_report = self._build_report(
            symbol=symbol,
            price_bars=price_bars,
            benchmark_bars=benchmark_bars,
            vix_history=vix_history,
            screener_history=screener_history,
        )
        return ResearchDataset(
            symbol=symbol,
            benchmark_symbol=benchmark_symbol,
            date_range=date_range,
            price_bars=price_bars,
            benchmark_bars=benchmark_bars,
            vix_history=vix_history,
            corporate_actions=corporate_actions,
            event_calendar=event_calendar,
            screener_history=screener_history,
            dataset_report=dataset_report,
        )

    def _build_report(
        self,
        symbol: str,
        price_bars: list[HistoricalPriceBar],
        benchmark_bars: list[HistoricalPriceBar],
        vix_history: dict[date, float],
        screener_history,
    ) -> DatasetQualityReport:
        dates = [bar.trade_date for bar in price_bars]
        assumptions_applied = [
            "screener_annual_points_assume_annual_report_plus_90d",
            "screener_quarterly_points_assume_quarterly_result_plus_45d",
            "next_session_execution_for_backtest",
        ]
        degraded_fields: list[str] = []
        unavailable_factor_families: list[str] = []
        if not benchmark_bars:
            unavailable_factor_families.append("benchmark")
            degraded_fields.append("benchmark_bars")
        if not vix_history:
            unavailable_factor_families.append("vix")
            degraded_fields.append("vix_history")
        if not getattr(screener_history, "fundamental_points", []):
            unavailable_factor_families.append("fundamentals")
            degraded_fields.append("fundamental_points")
        return DatasetQualityReport(
            symbol=symbol,
            first_available_date=min(dates) if dates else None,
            last_available_date=max(dates) if dates else None,
            missing_ranges=self._missing_ranges(dates),
            unavailable_factor_families=unavailable_factor_families,
            assumptions_applied=assumptions_applied,
            degraded_fields=degraded_fields,
        )

    def _missing_ranges(self, dates: list[date]) -> list[tuple[date, date]]:
        if len(dates) < 2:
            return []
        ordinals = [value.toordinal() for value in dates]
        gaps: list[tuple[date, date]] = []
        for previous, current in zip(ordinals, ordinals[1:]):
            if current - previous > 5:
                gaps.append((date.fromordinal(previous + 1), date.fromordinal(current - 1)))
        return gaps
