import unittest

from tradingbot.backtest.execution import BacktestExecutionAssumptions, CostModel


class CostModelTest(unittest.TestCase):
    def test_cost_model_applies_zerodha_style_cost_components(self) -> None:
        assumptions = BacktestExecutionAssumptions(
            brokerage_buy=0.0,
            brokerage_sell=0.0,
            stt_buy_bps=10.0,
            stt_sell_bps=10.0,
            exchange_txn_bps=0.307,
            sebi_per_crore=10.0,
            gst_pct=18.0,
            stamp_buy_bps=1.5,
            dp_charge_sell_flat=13.5,
            slippage_bps=5.0,
            impact_model="adv_fraction",
            impact_adv_fraction_cap=0.05,
        )
        model = CostModel(assumptions)

        buy = model.apply(price=100.0, quantity=100, direction="buy", adv_turnover=10000000.0)
        sell = model.apply(price=110.0, quantity=100, direction="sell", adv_turnover=10000000.0)

        self.assertGreater(buy.total_cost, 0.0)
        self.assertGreater(sell.total_cost, buy.total_cost)
        self.assertGreater(buy.effective_price, 100.0)
        self.assertGreater(sell.cost_breakdown["dp_charge"], 0.0)
