from tradingbot.core.models import TradeDecision


class PaperExecutor:
    def execute(self, decision: TradeDecision) -> dict:
        return {
            "decision_id": decision.decision_id,
            "symbol": decision.symbol,
            "status": decision.decision_status.value,
            "mode": decision.mode.name,
        }
