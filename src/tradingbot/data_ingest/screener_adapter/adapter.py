from __future__ import annotations

import json
import subprocess
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from tradingbot.core.enums import PeriodType
from tradingbot.core.models import (
    FundamentalSnapshot,
    HistoricalFundamentalPoint,
    HistoricalShareholdingPoint,
    ScreenerSnapshot,
)
from tradingbot.data_ingest.screener_adapter.fallback_parser import ScreenerFallbackParser
from tradingbot.data_ingest.screener_adapter.history_models import ScreenerHistoricalDataset


class ScreenerAdapter:
    def __init__(self, repo_root: str | Path) -> None:
        self.repo_root = Path(repo_root)
        self.script = self.repo_root / "src" / "tradingbot" / "data_ingest" / "screener_adapter" / "fetch_screener.mjs"
        self.fallback = ScreenerFallbackParser()
        self._snapshot_cache: dict[str, ScreenerSnapshot] = {}
        self._history_cache: dict[str, ScreenerHistoricalDataset] = {}

    def get_symbol_snapshot(self, symbol: str) -> ScreenerSnapshot:
        cached = self._snapshot_cache.get(symbol)
        if cached is not None:
            return cached
        try:
            process = subprocess.run(
                ["node", str(self.script), symbol],
                cwd=self.repo_root,
                check=True,
                capture_output=True,
                text=True,
                timeout=45,
            )
            payload = json.loads(process.stdout)
            shareholding = payload.get("shareholding", {})
            promoter_holding = float(shareholding.get("Promoters", 0.0))
            promoter_pledge = float(payload.get("pledgedPercentage", 0.0))
            snapshot = ScreenerSnapshot(
                symbol=symbol,
                analysis_pros=payload.get("analysis", {}).get("pros", []),
                analysis_cons=payload.get("analysis", {}).get("cons", []),
                shareholding=shareholding,
                fundamentals=FundamentalSnapshot(
                    sales_growth_yoy=float(payload.get("salesGrowthYoY", 0.0)),
                    profit_growth_yoy=float(payload.get("profitGrowthYoY", 0.0)),
                    operating_cashflow_trend=float(payload.get("operatingCashflowTrend", 0.0)),
                    roce=float(payload.get("roce", 0.0)),
                    roe=float(payload.get("roe", 0.0)),
                    debt_to_equity=float(payload.get("debtToEquity", 0.0)),
                    promoter_holding=promoter_holding,
                    promoter_pledge=promoter_pledge,
                ),
            )
            self._snapshot_cache[symbol] = snapshot
            return snapshot
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError):
            snapshot = self.fallback.get_symbol_snapshot(symbol)
            self._snapshot_cache[symbol] = snapshot
            return snapshot

    def get_symbol_history(self, symbol: str) -> ScreenerHistoricalDataset:
        cached = self._history_cache.get(symbol)
        if cached is not None:
            return cached
        try:
            process = subprocess.run(
                ["node", str(self.script), symbol, "--history"],
                cwd=self.repo_root,
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            payload = json.loads(process.stdout)
            history = self._history_from_payload(symbol, payload)
            self._history_cache[symbol] = history
            return history
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError, KeyError, TypeError, ValueError):
            url = f"https://www.screener.in/company/{symbol}/"
            import requests

            response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            response.raise_for_status()
            history = self.fallback.parse_history_from_html(symbol, response.text)
            self._history_cache[symbol] = history
            return history

    def _history_from_payload(self, symbol: str, payload: dict) -> ScreenerHistoricalDataset:
        if "html" in payload:
            return self.fallback.parse_history_from_html(symbol, payload["html"])
        if "raw_html" in payload:
            return self.fallback.parse_history_from_html(symbol, payload["raw_html"])
        data = payload["data"]
        shareholding_points = self._shareholding_points(symbol, data.get("shareholding"))
        ratio_points = self._table_points(symbol, data.get("ratios"), "ratios", PeriodType.ANNUAL, 90)
        latest_snapshot = self._latest_snapshot_from_data(data, shareholding_points)
        return ScreenerHistoricalDataset(
            symbol=symbol,
            static_pros=data.get("analysis", {}).get("pros", []),
            static_cons=data.get("analysis", {}).get("cons", []),
            static_metrics={
                section: {period: self._parse_numeric(value) for period, value in values.items()}
                for section, values in (data.get("CAGRs") or {}).items()
            },
            fundamental_points=ratio_points,
            shareholding_points=shareholding_points,
            latest_snapshot=latest_snapshot,
        )

    def _shareholding_points(self, symbol: str, table: dict | None) -> list[HistoricalShareholdingPoint]:
        if not table:
            return []
        points: list[HistoricalShareholdingPoint] = []
        headers = table.get("headers", [])
        rows = table.get("data", {})
        for metric_name, values in rows.items():
            for period in headers:
                period_end = self._parse_period_label(period)
                if period_end is None:
                    continue
                points.append(
                    HistoricalShareholdingPoint(
                        symbol=symbol,
                        metric_name=metric_name.replace("\xa0+", "").strip(),
                        value=self._parse_numeric(values.get(period, 0.0)),
                        period_end=period_end,
                        period_type=PeriodType.QUARTERLY,
                        source_label="shareholding",
                        availability_assumption="quarterly_result_plus_45d",
                        available_from=period_end + timedelta(days=45),
                    )
                )
        return sorted(points, key=lambda item: (item.period_end, item.metric_name))

    def _table_points(
        self,
        symbol: str,
        table: dict | None,
        source_label: str,
        period_type: PeriodType,
        lag_days: int,
    ) -> list[HistoricalFundamentalPoint]:
        if not table:
            return []
        points: list[HistoricalFundamentalPoint] = []
        headers = table.get("headers", [])
        rows = table.get("data", {})
        for metric_name, values in rows.items():
            for period in headers:
                period_end = self._parse_period_label(period)
                if period_end is None:
                    continue
                points.append(
                    HistoricalFundamentalPoint(
                        symbol=symbol,
                        metric_name=metric_name.strip(),
                        value=self._parse_numeric(values.get(period, 0.0)),
                        period_end=period_end,
                        period_type=period_type,
                        source_label=source_label,
                        availability_assumption="annual_report_plus_90d" if period_type == PeriodType.ANNUAL else "quarterly_result_plus_45d",
                        available_from=period_end + timedelta(days=lag_days),
                    )
                )
        return sorted(points, key=lambda item: (item.period_end, item.metric_name))

    def _latest_snapshot_from_data(
        self,
        data: dict,
        shareholding_points: list[HistoricalShareholdingPoint],
    ) -> FundamentalSnapshot:
        cagrs = data.get("CAGRs") or {}
        cash_flow_data = (data.get("cashFlow") or {}).get("data", {})
        balance_data = (data.get("balanceSheet") or {}).get("data", {})
        ratio_data = (data.get("ratios") or {}).get("data", {})
        ratio_headers = (data.get("ratios") or {}).get("headers", [])
        balance_headers = (data.get("balanceSheet") or {}).get("headers", [])
        cash_headers = (data.get("cashFlow") or {}).get("headers", [])
        latest_ratio = ratio_headers[-1] if ratio_headers else None
        latest_balance = balance_headers[-1] if balance_headers else None
        latest_cash = cash_headers[-1] if cash_headers else None
        latest_promoter = 0.0
        if shareholding_points:
            latest_period = max(point.period_end for point in shareholding_points)
            latest_promoter = next(
                (point.value for point in shareholding_points if point.period_end == latest_period and point.metric_name == "Promoters"),
                0.0,
            )
        borrowings = self._parse_numeric(balance_data.get("Borrowings", {}).get(latest_balance, 0.0)) if latest_balance else 0.0
        equity = self._parse_numeric(balance_data.get("Equity Capital", {}).get(latest_balance, 1.0)) if latest_balance else 1.0
        return FundamentalSnapshot(
            sales_growth_yoy=self._parse_numeric(cagrs.get("Compounded Sales Growth", {}).get("1 Year", 0.0)),
            profit_growth_yoy=self._parse_numeric(cagrs.get("Compounded Profit Growth", {}).get("1 Year", 0.0)),
            operating_cashflow_trend=self._parse_numeric(
                cash_flow_data.get("Cash from Operating Activity", {}).get(latest_cash, 0.0)
            )
            if latest_cash
            else 0.0,
            roce=self._parse_numeric(ratio_data.get("ROCE %", {}).get(latest_ratio, 0.0)) if latest_ratio else 0.0,
            roe=self._parse_numeric(cagrs.get("Return on Equity", {}).get("3 Years", 0.0)),
            debt_to_equity=round(borrowings / max(equity, 1.0), 4),
            promoter_holding=latest_promoter,
            promoter_pledge=0.0,
        )

    def _parse_period_label(self, label: str) -> date | None:
        for fmt in ("%b %Y", "%Y"):
            try:
                parsed = pd.to_datetime(str(label).strip(), format=fmt)
                if fmt == "%Y":
                    return date(parsed.year, 3, 31)
                return (pd.Timestamp(date(parsed.year, parsed.month, 1)) + pd.offsets.MonthEnd(0)).date()
            except (ValueError, TypeError):
                continue
        try:
            return pd.to_datetime(str(label).strip()).date()
        except Exception:
            return None

    def _parse_numeric(self, value) -> float:
        text = str(value).replace(",", "").replace("%", "").strip()
        if text in {"", "-", "None", "nan"}:
            return 0.0
        return float(text)
