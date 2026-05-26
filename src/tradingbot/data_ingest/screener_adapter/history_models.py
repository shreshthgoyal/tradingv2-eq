from __future__ import annotations

from dataclasses import dataclass

from tradingbot.core.models import FundamentalSnapshot, HistoricalFundamentalPoint, HistoricalShareholdingPoint


@dataclass
class ScreenerHistoricalDataset:
    symbol: str
    static_pros: list[str]
    static_cons: list[str]
    static_metrics: dict[str, dict[str, float]]
    fundamental_points: list[HistoricalFundamentalPoint]
    shareholding_points: list[HistoricalShareholdingPoint]
    latest_snapshot: FundamentalSnapshot
