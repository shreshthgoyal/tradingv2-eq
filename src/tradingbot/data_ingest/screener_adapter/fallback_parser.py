from __future__ import annotations

from io import StringIO
from datetime import date

import pandas as pd
import requests
from bs4 import BeautifulSoup

from tradingbot.core.enums import PeriodType
from tradingbot.core.models import (
    FundamentalSnapshot,
    HistoricalFundamentalPoint,
    HistoricalShareholdingPoint,
    ScreenerSnapshot,
)
from tradingbot.data_ingest.screener_adapter.history_models import ScreenerHistoricalDataset


class ScreenerFallbackParser:
    def get_symbol_snapshot(self, symbol: str) -> ScreenerSnapshot:
        url = f"https://www.screener.in/company/{symbol}/"
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        response.raise_for_status()
        history = self.parse_history_from_html(symbol, response.text)
        return ScreenerSnapshot(
            symbol=symbol,
            analysis_pros=history.static_pros,
            analysis_cons=history.static_cons,
            shareholding={
                point.metric_name: point.value
                for point in history.shareholding_points
                if point.period_end == max(p.period_end for p in history.shareholding_points)
            } if history.shareholding_points else {},
            fundamentals=history.latest_snapshot,
        )

    def parse_history_from_html(self, symbol: str, html: str) -> ScreenerHistoricalDataset:
        soup = BeautifulSoup(html, "html.parser")
        pros = [li.get_text(strip=True) for li in soup.select("#analysis .pros li")]
        cons = [li.get_text(strip=True) for li in soup.select("#analysis .cons li")]

        shareholding_history = self._table_history(soup, "shareholding")
        ratios_history = self._table_history(soup, "ratios")
        cashflow_history = self._table_history(soup, "cash-flow")
        balance_history = self._table_history(soup, "balance-sheet")
        cagrs = self._parse_cagrs(soup)

        shareholding_points = self._shareholding_points(symbol, shareholding_history)
        fundamental_points = self._fundamental_points(symbol, ratios_history)
        latest_period = max(balance_history.keys() or [date.today()])
        fundamentals = FundamentalSnapshot(
            sales_growth_yoy=self._parse_percent(cagrs.get("Compounded Sales Growth", {}).get("1 Year", "0")),
            profit_growth_yoy=self._parse_percent(cagrs.get("Compounded Profit Growth", {}).get("1 Year", "0")),
            operating_cashflow_trend=self._parse_number(cashflow_history.get(latest_period, {}).get("Cash from Operating Activity", 0)),
            roce=self._parse_percent(ratios_history.get(latest_period, {}).get("ROCE %", "0")),
            roe=self._parse_percent(cagrs.get("Return on Equity", {}).get("3 Years", "0")),
            debt_to_equity=self._compute_debt_to_equity(balance_history.get(latest_period, {})),
            promoter_holding=next((p.value for p in reversed(shareholding_points) if p.metric_name == "Promoters"), 0.0),
            promoter_pledge=0.0,
        )
        return ScreenerHistoricalDataset(
            symbol=symbol,
            static_pros=pros,
            static_cons=cons,
            static_metrics={name: {period: self._parse_percent(value) for period, value in values.items()} for name, values in cagrs.items()},
            fundamental_points=fundamental_points,
            shareholding_points=shareholding_points,
            latest_snapshot=fundamentals,
        )

    def _table_history(self, soup: BeautifulSoup, section_id: str) -> dict[date, dict[str, str]]:
        section = soup.select_one(f"#{section_id} table.data-table")
        if section is None:
            return {}
        dataframes = pd.read_html(StringIO(str(section)))
        if not dataframes:
            return {}
        frame = dataframes[0]
        if frame.empty:
            return {}
        frame.columns = [str(column).strip() for column in frame.columns]
        label_column = frame.columns[0]
        result: dict[date, dict[str, str]] = {}
        for column in frame.columns[1:]:
            period_end = self._parse_period_label(str(column).strip())
            if period_end is None:
                continue
            column_values: dict[str, str] = {}
            for _, row in frame.iterrows():
                label = str(row[label_column]).strip()
                if not label or label == "Raw PDF":
                    continue
                column_values[label] = str(row[column]).strip()
            result[period_end] = column_values
        return result

    def _parse_cagrs(self, soup: BeautifulSoup) -> dict[str, dict[str, str]]:
        data: dict[str, dict[str, str]] = {}
        for table in soup.select("#profit-loss table.ranges-table"):
            title = table.select_one("th")
            if title is None:
                continue
            rows: dict[str, str] = {}
            for row in table.select("tbody tr"):
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue
                rows[cells[0].get_text(strip=True).replace(":", "")] = cells[1].get_text(strip=True)
            if rows:
                data[title.get_text(strip=True)] = rows
        return data

    def _compute_debt_to_equity(self, balance: dict[str, str]) -> float:
        borrowings = self._parse_number(balance.get("Borrowings", 0))
        equity = self._parse_number(balance.get("Equity Capital", 1))
        return round(borrowings / max(equity, 1.0), 4)

    def _shareholding_points(self, symbol: str, history: dict[date, dict[str, str]]) -> list[HistoricalShareholdingPoint]:
        points: list[HistoricalShareholdingPoint] = []
        for period_end, metrics in sorted(history.items()):
            for metric_name, value in metrics.items():
                points.append(
                    HistoricalShareholdingPoint(
                        symbol=symbol,
                        metric_name=metric_name.replace("\xa0+", "").strip(),
                        value=self._parse_percent(value),
                        period_end=period_end,
                        period_type=PeriodType.QUARTERLY,
                        source_label="shareholding",
                        availability_assumption="quarterly_result_plus_45d",
                        available_from=self._add_days(period_end, 45),
                    )
                )
        return points

    def _fundamental_points(self, symbol: str, history: dict[date, dict[str, str]]) -> list[HistoricalFundamentalPoint]:
        points: list[HistoricalFundamentalPoint] = []
        for period_end, metrics in sorted(history.items()):
            for metric_name, value in metrics.items():
                points.append(
                    HistoricalFundamentalPoint(
                        symbol=symbol,
                        metric_name=metric_name,
                        value=self._parse_percent(value) if "%" in str(value) else self._parse_number(value),
                        period_end=period_end,
                        period_type=PeriodType.ANNUAL,
                        source_label="ratios",
                        availability_assumption="annual_report_plus_90d",
                        available_from=self._add_days(period_end, 90),
                    )
                )
        return points

    def _parse_period_label(self, label: str) -> date | None:
        label = label.strip()
        for fmt in ("%b %Y", "%Y"):
            try:
                parsed = pd.to_datetime(label, format=fmt)
                if fmt == "%Y":
                    return date(parsed.year, 3, 31)
                return (pd.Timestamp(date(parsed.year, parsed.month, 1)) + pd.offsets.MonthEnd(0)).date()
            except (ValueError, TypeError):
                continue
        try:
            parsed = pd.to_datetime(label)
            return parsed.date()
        except Exception:
            return None

    def _add_days(self, value: date, days: int) -> date:
        return (pd.Timestamp(value) + pd.Timedelta(days=days)).date()

    def _parse_percent(self, value: str) -> float:
        return self._parse_number(value.replace("%", ""))

    def _parse_number(self, value: str | float | int) -> float:
        text = str(value).replace(",", "").replace("%", "").strip()
        try:
            return float(text)
        except ValueError:
            return 0.0
