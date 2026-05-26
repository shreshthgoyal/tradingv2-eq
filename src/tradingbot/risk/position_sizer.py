from tradingbot.core.models import PriceBar


class PositionSizer:
    def size(self, bar: PriceBar, nav: float, cash: float, risk_per_trade_pct: float = 0.01) -> dict:
        atr_proxy = max((bar.high - bar.low), bar.close * 0.02)
        max_loss = nav * risk_per_trade_pct
        quantity = max(int(max_loss / max(atr_proxy * 2.0, 1.0)), 1)
        notional = quantity * bar.close
        if notional > cash:
            quantity = max(int(cash / max(bar.close, 1.0)), 0)
            notional = quantity * bar.close
        return {
            "atr_proxy": round(atr_proxy, 3),
            "position_size_qty": quantity,
            "position_size_notional": round(notional, 3),
            "initial_stop": round(bar.close - (atr_proxy * 2.0), 3),
            "trailing_stop": round(bar.close - (atr_proxy * 2.0), 3),
            "max_loss_expected": round(max_loss, 3),
        }
