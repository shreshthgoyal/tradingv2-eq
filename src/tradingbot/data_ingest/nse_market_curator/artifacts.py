from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from tradingbot.core.models import ArtifactManifest


class ArtifactExporter:
    def __init__(self, root: Path) -> None:
        self.root = root

    def export(self, result) -> ArtifactManifest:
        run_dir = self.root / result.summary.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        summary_json = run_dir / "summary.json"
        signals_json = run_dir / "signals.json"
        trades_json = run_dir / "trades.json"
        daily_states_json = run_dir / "daily_states.json"
        dataset_report_json = run_dir / "dataset_report.json"
        summary_markdown = run_dir / "summary.md"
        runbook_markdown = run_dir / "runbook.md"
        candidate_results_json = run_dir / "candidate_results.json"
        candidate_comparison_markdown = run_dir / "candidate_comparison.md"
        period_summary_markdown = run_dir / "period_summary.md"
        benchmark_scope_results_json = run_dir / "benchmark_scope_results.json"
        benchmark_scope_comparison_markdown = run_dir / "benchmark_scope_comparison.md"
        screening_summary_json = run_dir / "screening_summary.json"
        deployment_summary_json = run_dir / "deployment_summary.json"
        symbol_health_diagnostics_json = run_dir / "symbol_health_diagnostics.json"
        period_summary_paths: dict[str, str] = {}

        summary_json.write_text(json.dumps(self._serialize(result.summary), indent=2), encoding="utf-8")
        signals_json.write_text(json.dumps(self._serialize(result.signals), indent=2), encoding="utf-8")
        trades_json.write_text(json.dumps(self._serialize(result.trades), indent=2), encoding="utf-8")
        daily_states_json.write_text(json.dumps(self._serialize(result.daily_states), indent=2), encoding="utf-8")
        dataset_report_json.write_text(json.dumps(self._serialize(result.dataset_report), indent=2), encoding="utf-8")
        summary_markdown.write_text(self._summary_markdown(result), encoding="utf-8")
        runbook_markdown.write_text(self._runbook_markdown(result), encoding="utf-8")
        if result.candidate_results is not None:
            candidate_results_json.write_text(json.dumps(self._serialize(result.candidate_results), indent=2), encoding="utf-8")
            candidate_comparison_markdown.write_text(self._candidate_comparison_markdown(result), encoding="utf-8")
        if result.period_summaries:
            for level, payload in result.period_summaries.items():
                target = run_dir / f"period_summary_{level}.json"
                target.write_text(json.dumps(self._serialize(payload), indent=2), encoding="utf-8")
                period_summary_paths[level] = str(target)
            period_summary_markdown.write_text(self._period_summary_markdown(result), encoding="utf-8")
        if result.dataset_report.get("benchmark_scope_results"):
            benchmark_scope_results_json.write_text(json.dumps(self._serialize(result.dataset_report["benchmark_scope_results"]), indent=2), encoding="utf-8")
            benchmark_scope_comparison_markdown.write_text(self._benchmark_scope_markdown(result), encoding="utf-8")
        if result.dataset_report.get("screening_summary") is not None:
            screening_summary_json.write_text(json.dumps(self._serialize(result.dataset_report.get("screening_summary", {})), indent=2), encoding="utf-8")
        if result.dataset_report.get("deployment_summary") is not None:
            deployment_summary_json.write_text(json.dumps(self._serialize(result.dataset_report.get("deployment_summary", {})), indent=2), encoding="utf-8")
        if result.dataset_report.get("symbol_health_diagnostics") is not None:
            symbol_health_diagnostics_json.write_text(json.dumps(self._serialize(result.dataset_report.get("symbol_health_diagnostics", {})), indent=2), encoding="utf-8")

        return ArtifactManifest(
            run_id=result.summary.run_id,
            summary_json=str(summary_json),
            signals_json=str(signals_json),
            trades_json=str(trades_json),
            daily_states_json=str(daily_states_json),
            dataset_report_json=str(dataset_report_json),
            summary_markdown=str(summary_markdown),
            runbook_markdown=str(runbook_markdown),
            candidate_results_json=str(candidate_results_json) if result.candidate_results is not None else None,
            candidate_comparison_markdown=str(candidate_comparison_markdown) if result.candidate_results is not None else None,
            period_summary_paths=period_summary_paths or None,
            period_summary_markdown=str(period_summary_markdown) if result.period_summaries else None,
            benchmark_scope_results_json=str(benchmark_scope_results_json) if result.dataset_report.get("benchmark_scope_results") else None,
            benchmark_scope_comparison_markdown=str(benchmark_scope_comparison_markdown) if result.dataset_report.get("benchmark_scope_results") else None,
            screening_summary_json=str(screening_summary_json) if result.dataset_report.get("screening_summary") is not None else None,
            deployment_summary_json=str(deployment_summary_json) if result.dataset_report.get("deployment_summary") is not None else None,
            symbol_health_diagnostics_json=str(symbol_health_diagnostics_json) if result.dataset_report.get("symbol_health_diagnostics") is not None else None,
        )

    def _summary_markdown(self, result) -> str:
        metrics = result.summary.metrics
        weak_links = []
        if metrics.get("cagr", 0.0) <= 0:
            weak_links.append("Net edge is currently negative.")
        if metrics.get("turnover", 0.0) > 150.0:
            weak_links.append("Turnover is above the current target band.")
        if metrics.get("avg_holding_period_days", 0.0) < 5.0:
            weak_links.append("Holding periods are shorter than the configured minimum.")
        return "\n".join(
            [
                f"# Research Summary: {result.summary.symbol}",
                "",
                f"- Run ID: `{result.summary.run_id}`",
                f"- CAGR: `{metrics.get('cagr', 0.0):.4f}`",
                f"- Sharpe: `{metrics.get('sharpe', 0.0):.4f}`",
                f"- Sortino: `{metrics.get('sortino', 0.0):.4f}`",
                f"- Max drawdown: `{metrics.get('max_drawdown', 0.0):.4f}`",
                f"- Trades recorded: `{len(result.trades)}`",
                f"- Portfolio heat max: `{metrics.get('portfolio_heat_max', 0.0):.4f}`",
                f"- Winning candidate: `{metrics.get('winning_candidate', 'n/a')}`",
                f"- Winning status: `{metrics.get('winning_candidate_status', 'n/a')}`",
                f"- Best gross-edge candidate: `{metrics.get('best_gross_edge_candidate', 'n/a')}`",
                f"- Best net-edge candidate: `{metrics.get('best_net_edge_candidate', 'n/a')}`",
                f"- Best hold-quality candidate: `{metrics.get('best_hold_quality_candidate', 'n/a')}`",
                f"- Lowest drawdown-duration candidate: `{metrics.get('lowest_drawdown_duration_candidate', 'n/a')}`",
                f"- Most promising candidate: `{metrics.get('most_promising_candidate', 'n/a')}`",
                f"- Closest viability blocker: `{metrics.get('closest_to_viability_metric', 'n/a')}`",
                f"- Behavior style: `{metrics.get('behavior_style', 'unknown')}`",
                f"- Best aligned symbols: `{', '.join(metrics.get('best_aligned_symbols', []))}`",
                "",
                "## Current Weakest Links",
                *([f"- {line}" for line in weak_links] or ["- No obvious weak link summary generated."]),
                "",
                "## Symbol Recommendations",
                *[
                    f"- `{symbol}`: `{payload.get('recommendation', 'unknown')}`"
                    for symbol, payload in sorted(result.dataset_report.get("symbol_recommendations", {}).items())
                ],
            ]
        )

    def _runbook_markdown(self, result) -> str:
        return "\n".join(
            [
                "# Runbook",
                "",
                "This artifact set was generated by the phase-1 non-persistent research runner.",
                "",
                "Files:",
                "- `summary.json`: aggregate metrics and assumptions",
                "- `signals.json`: daily signal reasoning rows",
                "- `trades.json`: executed trade lifecycle rows",
                "- `daily_states.json`: daily NAV and position states",
                "- `dataset_report.json`: data coverage and degraded-field report",
                "- `candidate_results.json`: candidate-level metrics and status (phase 2)",
                "- `candidate_comparison.md`: compact candidate comparison table (phase 2)",
            ]
        )

    def _candidate_comparison_markdown(self, result) -> str:
        lines = ["# Candidate Comparison", "", "| Candidate | Status | Top Reason | CAGR | Sharpe | Max DD | Avg Hold | Leaders |", "|---|---:|---|---:|---:|---:|---:|---|"]
        for name, payload in sorted(result.candidate_results.items()):
            metrics = payload.get("metrics", {})
            top_reason = (payload.get("rejection_reasons") or [""])[0]
            assessment = payload.get("candidate_assessment", {})
            leaders = []
            if assessment.get("is_best_gross_edge_candidate"):
                leaders.append("gross")
            if assessment.get("is_best_net_edge_candidate"):
                leaders.append("net")
            if assessment.get("is_best_hold_quality_candidate"):
                leaders.append("hold")
            if assessment.get("is_lowest_drawdown_duration_candidate"):
                leaders.append("dd")
            if assessment.get("is_most_promising_candidate"):
                leaders.append("promise")
            lines.append(
                f"| {name} | {payload.get('status', 'UNKNOWN')} | {top_reason} | {metrics.get('cagr', 0.0):.4f} | {metrics.get('sharpe', 0.0):.4f} | {metrics.get('max_drawdown', 0.0):.4f} | {metrics.get('avg_holding_period_days', 0.0):.2f} | {', '.join(leaders)} |"
            )
        return "\n".join(lines)

    def _period_summary_markdown(self, result) -> str:
        lines = [
            "# Period Summary",
            "",
            "| Level | Label | Return | Sharpe | Trades | Avg Hold | Max DD | Strategy Mix |",
            "|---|---|---:|---:|---:|---:|---:|---|",
        ]
        for level in ["weekly", "monthly", "quarterly", "yearly", "overall"]:
            buckets = (result.period_summaries or {}).get(level, [])
            if not buckets:
                continue
            latest = buckets[-1]
            mix = ", ".join(f"{name}:{share:.2f}" for name, share in latest.get("selected_strategy_mix", {}).items())
            lines.append(
                f"| {level} | {latest.get('label', '')} | {latest.get('return_pct', 0.0):.4f} | {latest.get('sharpe', 0.0):.4f} | {latest.get('trade_count', 0.0):.0f} | {latest.get('avg_holding_period_days', 0.0):.2f} | {latest.get('max_drawdown', 0.0):.4f} | {mix} |"
            )
        return "\n".join(lines)

    def _benchmark_scope_markdown(self, result) -> str:
        lines = [
            "# Benchmark Scope Comparison",
            "",
            "| Scope | Status | Candidate | Blocker | Trades | Avg Hold | Net Edge | Concurrent | Excluded |",
            "|---|---|---|---|---:|---:|---:|---:|---|",
        ]
        for row in result.dataset_report.get("benchmark_scope_results", []):
            lines.append(
                f"| {row.get('scope_label')} | {row.get('scope_status')} | {row.get('candidate_winner')} | {row.get('blocker')} | {row.get('trade_count', 0.0):.0f} | {row.get('avg_holding_period_days', 0.0):.2f} | {row.get('net_edge', 0.0):.6f} | {row.get('avg_concurrent_positions', 0.0):.2f} | {', '.join(row.get('excluded_symbols', []))} |"
            )
        return "\n".join(lines)

    def _serialize(self, value: Any) -> Any:
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if hasattr(value, "value"):
            return value.value
        if is_dataclass(value):
            return {key: self._serialize(val) for key, val in asdict(value).items()}
        if isinstance(value, dict):
            return {key: self._serialize(val) for key, val in value.items()}
        if isinstance(value, list):
            return [self._serialize(item) for item in value]
        if isinstance(value, tuple):
            return [self._serialize(item) for item in value]
        return value
