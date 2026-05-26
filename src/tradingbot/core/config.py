from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from tradingbot.core.enums import Mode


@dataclass(slots=True)
class MongoConfig:
    uri: str
    database: str


@dataclass(slots=True)
class PortfolioConfig:
    starting_cash: float
    contribution_amount: float
    min_cash_buffer: float
    max_heat: float = 0.60
    max_symbol_weight: float = 0.30
    max_sector_weight: float = 0.50
    cash_buffer: float = 5000.0
    rebalance_frequency: str = "weekly"
    entry_staggering: bool = True


@dataclass(slots=True)
class RiskConfig:
    risk_per_trade_pct: float
    max_position_weight: float
    max_sector_weight: float
    max_portfolio_heat: float
    max_correlation: float
    atr_stop_multiplier: float


@dataclass(slots=True)
class LookbackConfig:
    short: int
    medium: int
    long: int


@dataclass(slots=True)
class StrategyConfig:
    entry_score_threshold: float
    hold_score_threshold: float
    time_stop_bars: int
    lookback_days: LookbackConfig


@dataclass(slots=True)
class UniverseConfig:
    symbols: list[str]
    benchmark_symbol: str
    max_active_positions: int = 3
    symbol_profiles: dict[str, dict[str, Any]] | None = None


@dataclass(slots=True)
class DashboardConfig:
    host: str
    port: int


@dataclass(slots=True)
class ScreenerConfig:
    base_url: str


@dataclass(slots=True)
class PathsConfig:
    local_eod_dir: str
    bhavcopy_dir: str


@dataclass(slots=True)
class ResearchConfig:
    candidate_set: str
    train_years: int
    test_years: int
    start_date: str | None
    end_date: str | None
    artifacts_dir: str
    use_common_start_date: bool
    summary_skill_path: str
    rejection: "ResearchRejectionConfig"
    rejection_profiles: "ResearchRejectionProfilesConfig"


@dataclass(slots=True)
class ResearchRejectionConfig:
    min_cagr: float
    min_sharpe: float
    min_profit_factor: float
    max_drawdown: float
    max_drawdown_duration_days: int
    max_turnover: float
    min_avg_holding_period_days: float
    max_oos_sharpe_drop_pct: float
    max_portfolio_heat: float
    min_trade_count: int


@dataclass(slots=True)
class ResearchRejectionProfilesConfig:
    hal_single_symbol: ResearchRejectionConfig
    deployable_three_symbol_benchmark: ResearchRejectionConfig
    portfolio_multi_symbol: ResearchRejectionConfig


@dataclass(slots=True)
class CostsConfig:
    brokerage_buy: float
    brokerage_sell: float
    stt_buy_bps: float
    stt_sell_bps: float
    exchange_txn_bps: float
    sebi_per_crore: float
    gst_pct: float
    stamp_buy_bps: float
    dp_charge_sell_flat: float
    slippage_bps: float
    impact_model: str
    impact_adv_fraction_cap: float


@dataclass(slots=True)
class SystemConfig:
    mode: Mode
    timezone: str
    mongo: MongoConfig
    portfolio: PortfolioConfig
    risk: RiskConfig
    strategy: StrategyConfig
    universe: UniverseConfig
    dashboard: DashboardConfig
    screener: ScreenerConfig
    paths: PathsConfig
    research: ResearchConfig
    costs: CostsConfig


def _map_config(data: dict[str, Any]) -> SystemConfig:
    research = data.get("research", {})
    costs = data.get("costs", {})
    portfolio = data["portfolio"]
    universe = data["universe"]
    return SystemConfig(
        mode=Mode(data["mode"]),
        timezone=data["timezone"],
        mongo=MongoConfig(**data["mongo"]),
        portfolio=PortfolioConfig(
            starting_cash=portfolio["starting_cash"],
            contribution_amount=portfolio["contribution_amount"],
            min_cash_buffer=portfolio["min_cash_buffer"],
            max_heat=portfolio.get("max_heat", 0.60),
            max_symbol_weight=portfolio.get("max_symbol_weight", 0.30),
            max_sector_weight=portfolio.get("max_sector_weight", 0.50),
            cash_buffer=portfolio.get("cash_buffer", portfolio.get("min_cash_buffer", 5000.0)),
            rebalance_frequency=portfolio.get("rebalance_frequency", "weekly"),
            entry_staggering=portfolio.get("entry_staggering", True),
        ),
        risk=RiskConfig(**data["risk"]),
        strategy=StrategyConfig(
            entry_score_threshold=data["strategy"]["entry_score_threshold"],
            hold_score_threshold=data["strategy"]["hold_score_threshold"],
            time_stop_bars=data["strategy"]["time_stop_bars"],
            lookback_days=LookbackConfig(**data["strategy"]["lookback_days"]),
        ),
        universe=UniverseConfig(
            symbols=universe["symbols"],
            benchmark_symbol=universe["benchmark_symbol"],
            max_active_positions=universe.get("max_active_positions", 3),
            symbol_profiles=universe.get("symbol_profiles", {}),
        ),
        dashboard=DashboardConfig(**data["dashboard"]),
        screener=ScreenerConfig(**data["screener"]),
        paths=PathsConfig(**data["paths"]),
        research=ResearchConfig(
            candidate_set=research.get("candidate_set", "default"),
            train_years=research.get("train_years", 3),
            test_years=research.get("test_years", 1),
            start_date=research.get("start_date"),
            end_date=research.get("end_date"),
            artifacts_dir=research.get("artifacts_dir", "artifacts"),
            use_common_start_date=research.get("use_common_start_date", True),
            summary_skill_path=research.get("summary_skill_path", "skills/current-system-state.md"),
            rejection=_build_rejection_config(research.get("rejection", {})),
            rejection_profiles=ResearchRejectionProfilesConfig(
                hal_single_symbol=_build_rejection_config(
                    research.get("rejection_profiles", {}).get("hal_single_symbol", research.get("rejection", {})),
                    defaults_override={
                        "max_drawdown_duration_days": 9999,
                        "min_trade_count": 10,
                    },
                ),
                deployable_three_symbol_benchmark=_build_rejection_config(
                    research.get("rejection_profiles", {}).get("deployable_three_symbol_benchmark", research.get("rejection", {})),
                    defaults_override={
                        "max_drawdown_duration_days": 365,
                        "min_trade_count": 8,
                        "min_avg_holding_period_days": 4.0,
                    },
                ),
                portfolio_multi_symbol=_build_rejection_config(
                    research.get("rejection_profiles", {}).get("portfolio_multi_symbol", research.get("rejection", {})),
                ),
            ),
        ),
        costs=CostsConfig(
            brokerage_buy=costs.get("brokerage_buy", 0.0),
            brokerage_sell=costs.get("brokerage_sell", 0.0),
            stt_buy_bps=costs.get("stt_buy_bps", 10.0),
            stt_sell_bps=costs.get("stt_sell_bps", 10.0),
            exchange_txn_bps=costs.get("exchange_txn_bps", 0.307),
            sebi_per_crore=costs.get("sebi_per_crore", 10.0),
            gst_pct=costs.get("gst_pct", 18.0),
            stamp_buy_bps=costs.get("stamp_buy_bps", 1.5),
            dp_charge_sell_flat=costs.get("dp_charge_sell_flat", 13.5),
            slippage_bps=costs.get("slippage_bps", 5.0),
            impact_model=costs.get("impact_model", "adv_fraction"),
            impact_adv_fraction_cap=costs.get("impact_adv_fraction_cap", 0.05),
        ),
    )


def _build_rejection_config(data: dict[str, Any], defaults_override: dict[str, Any] | None = None) -> ResearchRejectionConfig:
    defaults = {
        "min_cagr": 0.0,
        "min_sharpe": 0.0,
        "min_profit_factor": 1.0,
        "max_drawdown": 0.20,
        "max_drawdown_duration_days": 120,
        "max_turnover": 150.0,
        "min_avg_holding_period_days": 5.0,
        "max_oos_sharpe_drop_pct": 20.0,
        "max_portfolio_heat": 0.60,
        "min_trade_count": 5,
    }
    if defaults_override:
        defaults.update(defaults_override)
    return ResearchRejectionConfig(
        min_cagr=data.get("min_cagr", defaults["min_cagr"]),
        min_sharpe=data.get("min_sharpe", defaults["min_sharpe"]),
        min_profit_factor=data.get("min_profit_factor", defaults["min_profit_factor"]),
        max_drawdown=data.get("max_drawdown", defaults["max_drawdown"]),
        max_drawdown_duration_days=data.get("max_drawdown_duration_days", defaults["max_drawdown_duration_days"]),
        max_turnover=data.get("max_turnover", defaults["max_turnover"]),
        min_avg_holding_period_days=data.get("min_avg_holding_period_days", defaults["min_avg_holding_period_days"]),
        max_oos_sharpe_drop_pct=data.get("max_oos_sharpe_drop_pct", defaults["max_oos_sharpe_drop_pct"]),
        max_portfolio_heat=data.get("max_portfolio_heat", defaults["max_portfolio_heat"]),
        min_trade_count=data.get("min_trade_count", defaults["min_trade_count"]),
    )


def load_config(path: str | Path) -> SystemConfig:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return _map_config(data)
