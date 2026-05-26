from __future__ import annotations

from datetime import date

from tradingbot.core.models import SymbolSnapshot


class MarketCurator:
    def __init__(self, nse_adapter, screener_adapter) -> None:
        self.nse_adapter = nse_adapter
        self.screener_adapter = screener_adapter

    def curate_symbol(self, symbol: str, trade_date: date) -> SymbolSnapshot:
        nse_payload = self.nse_adapter.get_symbol_snapshot(symbol, trade_date)
        screener_payload = self.screener_adapter.get_symbol_snapshot(symbol)
        source_map = dict(nse_payload.get("source_map", {}))
        source_map["screener"] = ["fundamentals", "analysis", "shareholding"]
        return SymbolSnapshot(
            symbol=symbol,
            trade_date=trade_date,
            price_bar=nse_payload["price_bar"],
            market_context=nse_payload["market_context"],
            fundamentals=screener_payload.fundamentals,
            source_map=source_map,
        )
