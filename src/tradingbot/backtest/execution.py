from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RejectionProfile:
    min_cagr: float = 0.0
    min_sharpe: float = 0.0
    min_profit_factor: float = 1.0
    max_drawdown: float = 0.20
    max_drawdown_duration_days: int = 120
    max_turnover: float = 150.0
    min_avg_holding_period_days: float = 5.0
    max_oos_sharpe_drop_pct: float = 20.0
    max_portfolio_heat: float = 0.60
    min_trade_count: int = 5


@dataclass(slots=True)
class BacktestExecutionAssumptions:
    initial_cash: float = 100000.0
    slippage_bps: float = 10.0
    fee_bps: float = 5.0
    atr_stop_multiplier: float = 2.0
    time_stop_bars: int = 20
    brokerage_buy: float = 0.0
    brokerage_sell: float = 0.0
    stt_buy_bps: float = 10.0
    stt_sell_bps: float = 10.0
    exchange_txn_bps: float = 0.307
    sebi_per_crore: float = 10.0
    gst_pct: float = 18.0
    stamp_buy_bps: float = 1.5
    dp_charge_sell_flat: float = 13.5
    impact_model: str = "adv_fraction"
    impact_adv_fraction_cap: float = 0.05
    max_portfolio_heat: float = 0.60
    max_symbol_weight: float = 0.30
    max_active_positions: int = 3
    min_cagr: float = 0.0
    min_sharpe: float = 0.0
    min_profit_factor: float = 1.0
    max_drawdown: float = 0.20
    max_drawdown_duration_days: int = 120
    max_turnover: float = 150.0
    min_avg_holding_period_days: float = 5.0
    max_oos_sharpe_drop_pct: float = 20.0
    min_trade_count: int = 5

    def to_rejection_profile(self) -> RejectionProfile:
        return RejectionProfile(
            min_cagr=self.min_cagr,
            min_sharpe=self.min_sharpe,
            min_profit_factor=self.min_profit_factor,
            max_drawdown=self.max_drawdown,
            max_drawdown_duration_days=self.max_drawdown_duration_days,
            max_turnover=self.max_turnover,
            min_avg_holding_period_days=self.min_avg_holding_period_days,
            max_oos_sharpe_drop_pct=self.max_oos_sharpe_drop_pct,
            max_portfolio_heat=self.max_portfolio_heat,
            min_trade_count=self.min_trade_count,
        )


@dataclass(slots=True)
class TradeCost:
    effective_price: float
    total_cost: float
    cost_breakdown: dict[str, float]


class CostModel:
    def __init__(self, assumptions: BacktestExecutionAssumptions) -> None:
        self.assumptions = assumptions

    def apply(self, price: float, quantity: int, direction: str, adv_turnover: float = 0.0) -> TradeCost:
        notional = price * quantity
        slippage_cost = notional * (self.assumptions.slippage_bps / 10000.0)
        impact_bps = self._impact_bps(notional, adv_turnover)
        impact_cost = notional * (impact_bps / 10000.0)
        brokerage = self.assumptions.brokerage_buy if direction == "buy" else self.assumptions.brokerage_sell
        stt_bps = self.assumptions.stt_buy_bps if direction == "buy" else self.assumptions.stt_sell_bps
        stt = notional * (stt_bps / 10000.0)
        exchange_txn = notional * (self.assumptions.exchange_txn_bps / 10000.0)
        sebi = notional * (self.assumptions.sebi_per_crore / 10000000.0)
        stamp = notional * (self.assumptions.stamp_buy_bps / 10000.0) if direction == "buy" else 0.0
        dp_charge = self.assumptions.dp_charge_sell_flat if direction == "sell" else 0.0
        gst = (brokerage + exchange_txn + sebi) * (self.assumptions.gst_pct / 100.0)
        fallback_fee = notional * (self.assumptions.fee_bps / 10000.0)
        total_cost = slippage_cost + impact_cost + brokerage + stt + exchange_txn + sebi + stamp + dp_charge + gst + fallback_fee
        signed = 1 if direction == "buy" else -1
        effective_price = (notional + signed * total_cost) / max(quantity, 1)
        return TradeCost(
            effective_price=round(effective_price, 6),
            total_cost=round(total_cost, 6),
            cost_breakdown={
                "slippage": round(slippage_cost, 6),
                "impact": round(impact_cost, 6),
                "brokerage": round(brokerage, 6),
                "stt": round(stt, 6),
                "exchange_txn": round(exchange_txn, 6),
                "sebi": round(sebi, 6),
                "stamp": round(stamp, 6),
                "dp_charge": round(dp_charge, 6),
                "gst": round(gst, 6),
                "fallback_fee": round(fallback_fee, 6),
            },
        )

    def _impact_bps(self, notional: float, adv_turnover: float) -> float:
        if self.assumptions.impact_model != "adv_fraction" or adv_turnover <= 0:
            return 0.0
        participation = min(notional / adv_turnover, self.assumptions.impact_adv_fraction_cap)
        return round(participation / max(self.assumptions.impact_adv_fraction_cap, 1e-6) * 5.0, 6)
