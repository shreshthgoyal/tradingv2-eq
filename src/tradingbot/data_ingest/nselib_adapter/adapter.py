from __future__ import annotations

from contextlib import redirect_stdout
from datetime import date
from io import StringIO

import pandas as pd

from tradingbot.core.models import MarketContext, PriceBar
from tradingbot.core.models import HistoricalPriceBar, ResearchDateRange


def _to_float(value) -> float:
    text = str(value).replace(",", "").replace("%", "").replace("₹", "").strip()
    if text in {"", "-", "None", "nan"}:
        return 0.0
    return float(text)


class NseLibAdapter:
    def __init__(self) -> None:
        from nselib import capital_market

        self.capital_market = capital_market
        self._symbol_history_cache: dict[tuple[str, str, str], list[HistoricalPriceBar]] = {}
        self._benchmark_history_cache: dict[tuple[str, str, str], list[HistoricalPriceBar]] = {}
        self._vix_history_cache: dict[tuple[str, str], dict[date, float]] = {}
        self._event_calendar_frame_cache: dict[tuple[str, str], pd.DataFrame] = {}
        self._corporate_actions_frame_cache: dict[tuple[str, str], pd.DataFrame] = {}

    def get_symbol_snapshot(self, symbol: str, trade_date: date) -> dict:
        price_df = self.capital_market.price_volume_and_deliverable_position_data(symbol=symbol, period="1M")
        latest = price_df.iloc[-1]
        with redirect_stdout(StringIO()):
            index_df = self.capital_market.market_watch_all_indices()
        nifty = index_df[index_df["indexSymbol"] == "NIFTY 50"].iloc[0]
        vix_df = self.capital_market.india_vix_data(period="1M")
        vix_latest = vix_df.iloc[-1]
        return {
            "price_bar": PriceBar(
                symbol=symbol,
                trade_date=trade_date,
                open=_to_float(latest["OpenPrice"]),
                high=_to_float(latest["HighPrice"]),
                low=_to_float(latest["LowPrice"]),
                close=_to_float(latest["ClosePrice"]),
                volume=_to_float(latest["TotalTradedQuantity"]),
                turnover=_to_float(latest.get("TurnoverInRs", latest.get("Turnover₹", 0.0))),
                delivery_pct=_to_float(latest["%DlyQttoTradedQty"]),
            ),
            "market_context": MarketContext(
                benchmark_symbol="NIFTY 50",
                benchmark_close=_to_float(nifty["last"]),
                sector_name="UNKNOWN",
                sector_index_close=0.0,
                vix_close=_to_float(vix_latest["CLOSE_INDEX_VAL"]),
            ),
            "source_map": {"nselib": ["price_bar", "market_context"]},
        }

    def get_symbol_history(self, symbol: str, date_range: ResearchDateRange) -> list[HistoricalPriceBar]:
        key = (symbol, date_range.start_date.isoformat(), date_range.end_date.isoformat())
        cached = self._symbol_history_cache.get(key)
        if cached is not None:
            return cached
        with redirect_stdout(StringIO()):
            frame = self.capital_market.price_volume_and_deliverable_position_data(
                symbol=symbol,
                from_date=date_range.start_date.strftime("%d-%m-%Y"),
                to_date=date_range.end_date.strftime("%d-%m-%Y"),
            )
        bars = self._price_frame_to_bars(frame, symbol)
        self._symbol_history_cache[key] = bars
        return bars

    def get_benchmark_history(self, benchmark_symbol: str, date_range: ResearchDateRange) -> list[HistoricalPriceBar]:
        key = (benchmark_symbol, date_range.start_date.isoformat(), date_range.end_date.isoformat())
        cached = self._benchmark_history_cache.get(key)
        if cached is not None:
            return cached
        with redirect_stdout(StringIO()):
            frame = self.capital_market.index_data(
                index=benchmark_symbol,
                from_date=date_range.start_date.strftime("%d-%m-%Y"),
                to_date=date_range.end_date.strftime("%d-%m-%Y"),
            )
        if frame.empty:
            self._benchmark_history_cache[key] = []
            return []
        bars: list[HistoricalPriceBar] = []
        for _, row in frame.iterrows():
            bars.append(
                HistoricalPriceBar(
                    symbol=benchmark_symbol,
                    trade_date=pd.to_datetime(row["TIMESTAMP"], format="%d-%b-%Y").date(),
                    open=_to_float(row["OPEN_INDEX_VAL"]),
                    high=_to_float(row["HIGH_INDEX_VAL"]),
                    low=_to_float(row["LOW_INDEX_VAL"]),
                    close=_to_float(row["CLOSE_INDEX_VAL"]),
                    volume=_to_float(row.get("TRADED_QTY", 0.0)),
                    turnover=_to_float(row.get("TURN_OVER", 0.0)),
                    delivery_pct=0.0,
                )
            )
        result = sorted(bars, key=lambda item: item.trade_date)
        self._benchmark_history_cache[key] = result
        return result

    def get_vix_history(self, date_range: ResearchDateRange) -> dict[date, float]:
        key = (date_range.start_date.isoformat(), date_range.end_date.isoformat())
        cached = self._vix_history_cache.get(key)
        if cached is not None:
            return cached
        with redirect_stdout(StringIO()):
            frame = self.capital_market.india_vix_data(
                from_date=date_range.start_date.strftime("%d-%m-%Y"),
                to_date=date_range.end_date.strftime("%d-%m-%Y"),
            )
        if frame.empty:
            self._vix_history_cache[key] = {}
            return {}
        history: dict[date, float] = {}
        for _, row in frame.iterrows():
            history[pd.to_datetime(row["TIMESTAMP"], format="%d-%b-%Y").date()] = _to_float(row["CLOSE_INDEX_VAL"])
        self._vix_history_cache[key] = history
        return history

    def get_event_calendar(self, symbol: str, date_range: ResearchDateRange) -> dict[date, list[dict]]:
        key = (date_range.start_date.isoformat(), date_range.end_date.isoformat())
        frame = self._event_calendar_frame_cache.get(key)
        if frame is None:
            with redirect_stdout(StringIO()):
                frame = self.capital_market.event_calendar_for_equity(
                    from_date=date_range.start_date.strftime("%d-%m-%Y"),
                    to_date=date_range.end_date.strftime("%d-%m-%Y"),
                )
            self._event_calendar_frame_cache[key] = frame
        return self._filter_symbol_events(frame, symbol)

    def get_corporate_actions(self, symbol: str, date_range: ResearchDateRange) -> dict[date, list[dict]]:
        key = (date_range.start_date.isoformat(), date_range.end_date.isoformat())
        frame = self._corporate_actions_frame_cache.get(key)
        if frame is None:
            with redirect_stdout(StringIO()):
                frame = self.capital_market.corporate_actions_for_equity(
                    from_date=date_range.start_date.strftime("%d-%m-%Y"),
                    to_date=date_range.end_date.strftime("%d-%m-%Y"),
                )
            self._corporate_actions_frame_cache[key] = frame
        return self._filter_symbol_events(frame, symbol)

    def _price_frame_to_bars(self, frame, symbol: str) -> list[HistoricalPriceBar]:
        if frame.empty:
            return []
        bars: list[HistoricalPriceBar] = []
        for _, row in frame.iterrows():
            symbol_value = row.get('ï»¿"Symbol"', row.get("Symbol", symbol))
            bars.append(
                HistoricalPriceBar(
                    symbol=str(symbol_value).replace('"', ""),
                    trade_date=pd.to_datetime(row["Date"], format="%d-%b-%Y").date(),
                    open=_to_float(row["OpenPrice"]),
                    high=_to_float(row["HighPrice"]),
                    low=_to_float(row["LowPrice"]),
                    close=_to_float(row["ClosePrice"]),
                    volume=_to_float(row["TotalTradedQuantity"]),
                    turnover=_to_float(row.get("TurnoverInRs", 0.0)),
                    delivery_pct=_to_float(row.get("%DlyQttoTradedQty", 0.0)),
                )
            )
        return sorted(bars, key=lambda item: item.trade_date)

    def _filter_symbol_events(self, frame, symbol: str) -> dict[date, list[dict]]:
        if frame.empty:
            return {}
        symbol_candidates = {"symbol", "SYMBOL", "Symbol", 'ï»¿"Symbol"', "SM_SYMBOL", "NSE Symbol"}
        date_candidates = ["exDate", "Ex Date", "date", "Date", "TIMESTAMP", "BM_date"]
        result: dict[date, list[dict]] = {}
        for _, row in frame.iterrows():
            row_dict = {str(key): value for key, value in row.to_dict().items()}
            row_symbol = None
            for key in symbol_candidates:
                if key in row_dict and str(row_dict[key]).strip().upper() == symbol.upper():
                    row_symbol = symbol
                    break
            if row_symbol is None:
                continue
            row_date = None
            for key in date_candidates:
                if key in row_dict and str(row_dict[key]).strip():
                    try:
                        row_date = pd.to_datetime(row_dict[key], dayfirst=True).date()
                        break
                    except Exception:
                        continue
            if row_date is None:
                continue
            result.setdefault(row_date, []).append(row_dict)
        return result
