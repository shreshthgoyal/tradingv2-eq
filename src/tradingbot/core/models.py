from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any

from tradingbot.core.enums import (
    CandidateStatus,
    DecisionStatus,
    DecisionType,
    Mode,
    PeriodType,
    RegimeLabel,
    SignalState,
)


@dataclass(slots=True)
class PriceBar:
    symbol: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float
    delivery_pct: float = 0.0


@dataclass(slots=True)
class MarketContext:
    benchmark_symbol: str
    benchmark_close: float
    sector_name: str
    sector_index_close: float
    vix_close: float


@dataclass(slots=True)
class FundamentalSnapshot:
    sales_growth_yoy: float
    profit_growth_yoy: float
    operating_cashflow_trend: float
    roce: float
    roe: float
    debt_to_equity: float
    promoter_holding: float
    promoter_pledge: float


@dataclass(slots=True)
class ScreenerSnapshot:
    symbol: str
    analysis_pros: list[str]
    analysis_cons: list[str]
    shareholding: dict[str, float]
    fundamentals: FundamentalSnapshot


@dataclass(slots=True)
class SymbolSnapshot:
    symbol: str
    trade_date: date
    price_bar: PriceBar
    market_context: MarketContext
    fundamentals: FundamentalSnapshot
    source_map: dict[str, list[str]]
    degraded_mode: bool = False
    missing_fields: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RegimeInput:
    benchmark_above_200dma: bool
    benchmark_trend_strength: float
    breadth_strength: float
    vix_level: float
    sector_strength: float
    flow_strength: float


@dataclass(slots=True)
class RegimeState:
    label: RegimeLabel
    confidence: float
    factors: dict[str, float]


@dataclass(slots=True)
class TradeDecision:
    decision_id: str
    run_id: str
    strategy_version: str
    config_hash: str
    mode: Mode
    decision: DecisionType
    decision_status: DecisionStatus
    symbol: str
    trade_date: date
    effective_session: str
    regime: dict[str, Any]
    screening: dict[str, Any]
    scores: dict[str, Any]
    market_data: dict[str, Any]
    fundamentals: dict[str, Any]
    portfolio_context: dict[str, Any]
    risk_plan: dict[str, Any]
    execution_plan: dict[str, Any]
    reason_codes: list[str]
    human_reason: str
    created_at_ist: datetime

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["mode"] = self.mode.name
        payload["decision"] = self.decision.value
        payload["decision_status"] = self.decision_status.value
        payload["trade_date"] = self.trade_date.isoformat()
        payload["created_at_ist"] = self.created_at_ist.isoformat()
        return payload


@dataclass(slots=True)
class ResearchDateRange:
    start_date: date
    end_date: date


@dataclass(slots=True)
class HistoricalPriceBar:
    symbol: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float
    delivery_pct: float = 0.0


@dataclass(slots=True)
class HistoricalFundamentalPoint:
    symbol: str
    metric_name: str
    value: float
    period_end: date
    period_type: PeriodType
    source_label: str
    availability_assumption: str
    available_from: date


@dataclass(slots=True)
class HistoricalShareholdingPoint:
    symbol: str
    metric_name: str
    value: float
    period_end: date
    period_type: PeriodType
    source_label: str
    availability_assumption: str
    available_from: date


@dataclass(slots=True)
class RegimeObservation:
    symbol: str
    trade_date: date
    label: RegimeLabel
    confidence: float
    factors: dict[str, float]
    degraded_factors: list[str]


@dataclass(slots=True)
class ScreeningObservation:
    symbol: str
    trade_date: date
    investable: bool
    passed_checks: list[str]
    failed_checks: list[str]
    risk_flags: list[str]
    score: float
    degraded: bool = False


@dataclass(slots=True)
class IndicatorSnapshot:
    symbol: str
    trade_date: date
    values: dict[str, float]


@dataclass(slots=True)
class SignalObservation:
    symbol: str
    trade_date: date
    state: str
    module_scores: dict[str, float]
    composite_score: float
    threshold: float
    reasons: list[str]
    screening_pass: bool = False
    screening_blockers: list[str] = field(default_factory=list)
    soft_blockers: list[str] = field(default_factory=list)
    regime_state: str = "hard_block"
    entry_band: str | None = None
    entry_blockers: list[str] = field(default_factory=list)
    score_margin: float = 0.0
    screening_details: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class BacktestTrade:
    symbol: str
    entry_date: date
    exit_date: date | None
    entry_price: float
    exit_price: float | None
    quantity: int
    pnl: float
    decision: dict[str, Any]
    holding_period_days: int = 0
    gross_pnl: float = 0.0
    total_cost: float = 0.0


@dataclass(slots=True)
class BacktestDailyState:
    trade_date: date
    cash: float
    position_qty: int | dict[str, int]
    close_price: float | dict[str, float]
    nav: float
    regime_label: str
    signal_state: str
    portfolio_heat: float = 0.0
    exposure: float = 0.0
    selected_strategy: str | None = None
    exit_policy: str | None = None
    exit_severity: str | None = None
    position_stage: str | None = None
    profit_state: str | None = None
    regime_deterioration_level: str | None = None


@dataclass(slots=True)
class BacktestSummary:
    run_id: str
    symbol: str
    metrics: dict[str, float]
    assumptions: dict[str, Any]


@dataclass(slots=True)
class ArtifactManifest:
    run_id: str
    summary_json: str
    signals_json: str
    trades_json: str
    daily_states_json: str
    dataset_report_json: str
    summary_markdown: str
    runbook_markdown: str
    candidate_results_json: str | None = None
    candidate_comparison_markdown: str | None = None
    period_summary_paths: dict[str, str] | None = None
    period_summary_markdown: str | None = None
    benchmark_scope_results_json: str | None = None
    benchmark_scope_comparison_markdown: str | None = None
    screening_summary_json: str | None = None
    deployment_summary_json: str | None = None
    symbol_health_diagnostics_json: str | None = None


@dataclass(slots=True)
class WindowMetrics:
    window_label: str
    in_sample_metrics: dict[str, float]
    out_of_sample_metrics: dict[str, float]


@dataclass(slots=True)
class CandidateEvaluation:
    name: str
    status: CandidateStatus
    rejection_reasons: list[str]
    enabled_modules: list[str]
    disabled_modules: list[str]
    effective_start_date: date | None
    oos_summary: dict[str, float]
    is_summary: dict[str, float]
    metrics: dict[str, float]
    window_metrics: list[WindowMetrics]
    symbol_recommendations: dict[str, dict[str, Any]] = field(default_factory=dict)
    hal_research_status: str = "RESEARCH_BLOCKED"
    portfolio_readiness_status: str = "PORTFOLIO_BLOCKED"
    hal_single_symbol_binding_blocker: str = "unknown"
    portfolio_ready_binding_blocker: str = "unknown"


@dataclass(slots=True)
class PortfolioResearchSummary:
    winning_candidate: str | None
    winning_candidate_status: CandidateStatus | None
    requested_start_date: date | None
    effective_portfolio_start_date: date | None


@dataclass(slots=True)
class RunStateSummary:
    run_timestamp: datetime
    run_id: str
    universe: list[str]
    requested_start_date: date | None
    effective_start_date: date | None
    winning_candidate: str | None
    winning_candidate_status: CandidateStatus | None
    best_gross_edge_candidate: str | None = None
    best_net_edge_candidate: str | None = None
    best_hold_quality_candidate: str | None = None
    lowest_drawdown_duration_candidate: str | None = None
    most_promising_candidate: str | None = None
    metrics: dict[str, float] = field(default_factory=dict)
    interpretation: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ResearchDataset:
    symbol: str
    benchmark_symbol: str
    date_range: ResearchDateRange
    price_bars: list[HistoricalPriceBar]
    benchmark_bars: list[HistoricalPriceBar]
    vix_history: dict[date, float]
    corporate_actions: dict[date, list[dict[str, Any]]]
    event_calendar: dict[date, list[dict[str, Any]]]
    screener_history: Any
    dataset_report: Any
