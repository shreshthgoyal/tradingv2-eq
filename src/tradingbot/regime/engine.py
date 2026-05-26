from tradingbot.core.enums import RegimeLabel
from tradingbot.core.models import RegimeInput, RegimeState


class RegimeEngine:
    def classify(self, regime_input: RegimeInput) -> RegimeState:
        score = (
            regime_input.benchmark_trend_strength
            + regime_input.breadth_strength
            + regime_input.sector_strength
            + regime_input.flow_strength
        ) / 4.0
        if regime_input.vix_level > 22:
            volatility_score = 0.2
        elif regime_input.vix_level > 18:
            volatility_score = 0.4
        else:
            volatility_score = 0.8

        confidence = round((score + volatility_score) / 2.0, 3)
        if regime_input.benchmark_above_200dma:
            label = (
                RegimeLabel.BULL_TRENDING
                if score >= 0.6 and volatility_score >= 0.5
                else RegimeLabel.BULL_RANGING
            )
        else:
            label = (
                RegimeLabel.BEAR_TRENDING
                if score < 0.4 or volatility_score < 0.4
                else RegimeLabel.BEAR_RANGING
            )
        return RegimeState(
            label=label,
            confidence=confidence,
            factors={
                "benchmark_trend": regime_input.benchmark_trend_strength,
                "breadth": regime_input.breadth_strength,
                "volatility": volatility_score,
                "sector_strength": regime_input.sector_strength,
                "flow_state": regime_input.flow_strength,
            },
        )
