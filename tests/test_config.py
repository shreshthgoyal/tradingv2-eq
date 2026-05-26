import tempfile
import unittest
from pathlib import Path

from tradingbot.core.config import load_config


class ConfigTest(unittest.TestCase):
    def test_load_config_parses_nested_yaml(self) -> None:
        yaml_text = """
mode: paper
timezone: Asia/Kolkata
mongo:
  uri: mongodb://localhost:27017
  database: tradingbot
portfolio:
  starting_cash: 100000
  contribution_amount: 1000
  min_cash_buffer: 5000
risk:
  risk_per_trade_pct: 0.01
  max_position_weight: 0.30
  max_sector_weight: 0.50
  max_portfolio_heat: 0.05
  max_correlation: 0.80
  atr_stop_multiplier: 2.0
strategy:
  entry_score_threshold: 0.55
  hold_score_threshold: 0.45
  time_stop_bars: 20
  lookback_days:
    short: 20
    medium: 63
    long: 200
universe:
  symbols: [HAL]
  benchmark_symbol: NIFTY 50
  max_active_positions: 3
dashboard:
  host: 127.0.0.1
  port: 8000
screener:
  base_url: https://www.screener.in/company
paths:
  local_eod_dir: data/eod
  bhavcopy_dir: data/bhavcopy
research:
  candidate_set: default
  train_years: 3
  test_years: 1
  start_date:
  end_date:
  artifacts_dir: artifacts
costs:
  brokerage_buy: 0.0
  brokerage_sell: 0.0
  stt_buy_bps: 10.0
  stt_sell_bps: 10.0
  exchange_txn_bps: 0.307
  sebi_per_crore: 10.0
  gst_pct: 18.0
  stamp_buy_bps: 1.5
  dp_charge_sell_flat: 13.5
  slippage_bps: 5.0
  impact_model: adv_fraction
  impact_adv_fraction_cap: 0.05
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "system.yaml"
            path.write_text(yaml_text)
            config = load_config(path)

        self.assertEqual(config.mode.value, "paper")
        self.assertEqual(config.universe.symbols, ["HAL"])
        self.assertEqual(config.strategy.lookback_days.long, 200)
        self.assertEqual(config.risk.atr_stop_multiplier, 2.0)
        self.assertEqual(config.universe.max_active_positions, 3)
        self.assertEqual(config.research.candidate_set, "default")
        self.assertEqual(config.costs.stt_buy_bps, 10.0)
        self.assertEqual(config.research.rejection_profiles.hal_single_symbol.min_trade_count, 10)
        self.assertEqual(config.research.rejection_profiles.deployable_three_symbol_benchmark.min_trade_count, 8)
        self.assertEqual(config.research.rejection_profiles.deployable_three_symbol_benchmark.max_drawdown_duration_days, 365)
