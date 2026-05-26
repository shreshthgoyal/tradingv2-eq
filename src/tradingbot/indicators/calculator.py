from tradingbot.core.models import SymbolSnapshot


class IndicatorCalculator:
    def score(self, snapshot: SymbolSnapshot, regime_label: str) -> dict:
        bar = snapshot.price_bar
        fundamentals = snapshot.fundamentals
        liquidity_score = min(bar.turnover / 500000000.0, 1.0)
        quality_score = min((fundamentals.roce + fundamentals.roe) / 60.0, 1.0)
        fundamental_score = min(
            (fundamentals.sales_growth_yoy + fundamentals.profit_growth_yoy) / 40.0,
            1.0,
        )
        trend_score = 0.8 if bar.close > bar.open else 0.35
        timing_score = 0.75 if bar.close >= (bar.high + bar.low) / 2.0 else 0.4
        relative_strength_score = 0.7 if snapshot.market_context.vix_close < 20 else 0.45
        regime_fit_score = 0.8 if regime_label == "BULL_TRENDING" else 0.45
        risk_penalty = 0.05 if fundamentals.promoter_pledge == 0 else 0.15
        correlation_penalty = 0.05
        event_risk_penalty = 0.05
        composite_score = round(
            (
                trend_score
                + timing_score
                + quality_score
                + fundamental_score
                + relative_strength_score
                + liquidity_score
                + regime_fit_score
            )
            / 7.0
            - risk_penalty
            - correlation_penalty
            - event_risk_penalty,
            3,
        )
        return {
            "trend_score": round(trend_score, 3),
            "timing_score": round(timing_score, 3),
            "quality_score": round(quality_score, 3),
            "fundamental_score": round(fundamental_score, 3),
            "relative_strength_score": round(relative_strength_score, 3),
            "liquidity_score": round(liquidity_score, 3),
            "regime_fit_score": round(regime_fit_score, 3),
            "risk_penalty": round(risk_penalty, 3),
            "correlation_penalty": round(correlation_penalty, 3),
            "event_risk_penalty": round(event_risk_penalty, 3),
            "composite_score": composite_score,
        }
