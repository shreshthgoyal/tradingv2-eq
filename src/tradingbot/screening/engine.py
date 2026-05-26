from tradingbot.core.models import SymbolSnapshot


class ScreeningEngine:
    def evaluate(self, snapshot: SymbolSnapshot) -> dict:
        passed_checks = []
        failed_checks = []
        risk_flags = []
        bar = snapshot.price_bar
        fundamentals = snapshot.fundamentals

        if bar.turnover >= 100000000:
            passed_checks.append("LIQUIDITY_OK")
        else:
            failed_checks.append("LIQUIDITY_LOW")
        if bar.delivery_pct >= 25:
            passed_checks.append("DELIVERY_OK")
        else:
            failed_checks.append("DELIVERY_LOW")
        if fundamentals.promoter_pledge <= 20:
            passed_checks.append("PROMOTER_PLEDGE_OK")
        else:
            failed_checks.append("PROMOTER_PLEDGE_HIGH")
        if fundamentals.debt_to_equity <= 1.0:
            passed_checks.append("BALANCE_SHEET_OK")
        else:
            failed_checks.append("BALANCE_SHEET_WEAK")

        investable = not failed_checks
        score = len(passed_checks) / max(len(passed_checks) + len(failed_checks), 1)
        if snapshot.degraded_mode:
            risk_flags.append("DEGRADED_MODE")
        return {
            "investable": investable,
            "passed_checks": passed_checks,
            "failed_checks": failed_checks,
            "risk_flags": risk_flags,
            "screen_score": round(score, 3),
        }
