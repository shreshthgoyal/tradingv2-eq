from __future__ import annotations

from datetime import date
from pathlib import Path

from tradingbot.core.config import load_config
from tradingbot.core.models import RegimeInput
from tradingbot.data_ingest.fallbacks.fii_dii import FiiDiiFallback
from tradingbot.data_ingest.nse_market_curator.curator import MarketCurator
from tradingbot.data_ingest.nselib_adapter.adapter import NseLibAdapter
from tradingbot.data_ingest.screener_adapter.adapter import ScreenerAdapter
from tradingbot.regime.engine import RegimeEngine
from tradingbot.strategy.engine import StrategyEngine


def run_daily(config_path: str | Path) -> list[dict]:
    config = load_config(config_path)
    nse_adapter = NseLibAdapter()
    screener_adapter = ScreenerAdapter(Path(config_path).resolve().parents[1])
    curator = MarketCurator(nse_adapter, screener_adapter)
    regime_engine = RegimeEngine()
    strategy_engine = StrategyEngine()
    flow_fallback = FiiDiiFallback()

    regime = regime_engine.classify(
        RegimeInput(
            benchmark_above_200dma=True,
            benchmark_trend_strength=0.7,
            breadth_strength=0.6,
            vix_level=16.0,
            sector_strength=0.6,
            flow_strength=flow_fallback.latest_flow_strength(),
        )
    )

    decisions = []
    for symbol in config.universe.symbols:
        snapshot = curator.curate_symbol(symbol, date.today())
        decision = strategy_engine.evaluate(
            snapshot,
            regime,
            nav=config.portfolio.starting_cash,
            cash=config.portfolio.starting_cash + config.portfolio.contribution_amount,
        )
        decisions.append(decision.to_dict())
    return decisions
