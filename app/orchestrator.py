"""End-to-end decision pipeline.

Wires the analysis agents, the Decision Agent, the deterministic Risk Engine
and the Order Manager into a single orchestrated flow:

    Technical Analysis -> Decision -> Risk Engine -> Order Manager

The pipeline is the same in every mode; only the final step differs. In
simulated modes (BACKTEST/SHADOW) an approved trade is filled by the paper
simulator. In CAPITAL_DEMO/LIVE_DISABLED the flow stops before execution
(read-only): nothing is ever sent to the broker.

Honours the rule that a trade must not proceed if its audit record cannot be
saved: the pre-trade audit write is attempted before the Risk Engine runs, and
its failure causes a deterministic rejection.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Sequence

from agents.candles import Candle
from agents.decision_agent import Decision, DecisionAgent, DecisionOutcome, ScoreInputs
from agents.news_macro import MacroEvent, NewsMacroAgent
from agents.technical_analysis import TechnicalAnalysisAgent, TechnicalSignal
from app.config import AppConfig
from app.errors import LiveTradingDisabledError
from app.logging_utils import get_logger
from app.modes import SIMULATED_MODES, OperatingMode
from backtesting.paper_simulator import PaperCFDSimulator
from capital.models import Price
from execution.order_manager import OrderManager, OrderResult
from risk.engine import RiskDecision, RiskEngine
from risk.models import Direction, OpenPosition, PortfolioState, TradeProposal

logger = get_logger(__name__)

AuditSink = Callable[[dict[str, Any]], None]


class PipelineState(str, Enum):
    """Terminal state of a single symbol run."""

    NO_TRADE = "NO_TRADE"
    WAIT = "WAIT"
    WATCHLIST = "WATCHLIST"
    RISK_REJECTED = "RISK_REJECTED"
    READONLY_SKIPPED = "READONLY_SKIPPED"
    EXECUTED = "EXECUTED"


@dataclass(frozen=True)
class MarketSnapshot:
    """All inputs the pipeline needs for one symbol at one point in time."""

    symbol: str
    candles_1h: Sequence[Candle]
    candles_15m: Sequence[Candle]
    price: Price | None = None
    # External agent scores (defaults are neutral until those agents exist).
    news_score: float = 0.5
    sentiment_score: float = 0.5
    portfolio_fit_score: float | None = None  # computed if None
    # Gates.
    news_conflict: bool = False
    # Macro events for the News Macro Agent (used when a news_agent is set).
    macro_events: Sequence[MacroEvent] = ()
    # Optional explicit market-quality overrides (else derived from price).
    spread: float | None = None
    data_age_seconds: float | None = None
    now: datetime | None = None


@dataclass(frozen=True)
class PipelineResult:
    symbol: str
    state: PipelineState
    technical: TechnicalSignal
    decision: Decision
    risk: RiskDecision | None = None
    order: OrderResult | None = None
    proposal: TradeProposal | None = None
    audit: dict[str, Any] = field(default_factory=dict)


class Orchestrator:
    """Runs the decision pipeline for one or more symbols."""

    def __init__(
        self,
        config: AppConfig,
        *,
        mode: OperatingMode | None = None,
        simulator: PaperCFDSimulator | None = None,
        starting_equity: float = 10_000.0,
        technical_agent: TechnicalAnalysisAgent | None = None,
        decision_agent: DecisionAgent | None = None,
        news_agent: NewsMacroAgent | None = None,
        risk_engine: RiskEngine | None = None,
        order_manager: OrderManager | None = None,
        audit_sink: AuditSink | None = None,
    ) -> None:
        self._config = config
        self._mode = mode or config.mode
        self._simulator = simulator
        self._starting_equity = starting_equity
        self._technical = technical_agent or TechnicalAnalysisAgent()
        self._decision = decision_agent or DecisionAgent()
        self._news = news_agent
        self._risk = risk_engine or RiskEngine(config.risk)
        self._order_manager = order_manager or OrderManager(self._mode, simulator)
        self.audit_log: list[dict[str, Any]] = []
        self._audit_sink: AuditSink = audit_sink or self.audit_log.append
        self._bucket_of = {
            inst.symbol: inst.bucket for inst in config.instruments.instruments
        }
        # Snapshot of equity at the start of the trading day (for daily stops).
        self._day_start_equity = starting_equity

    # -- public API --------------------------------------------------------

    def run(
        self,
        snapshots: Sequence[MarketSnapshot],
        marks: dict[str, float] | None = None,
    ) -> list[PipelineResult]:
        return [self.run_symbol(s, marks) for s in snapshots]

    def run_symbol(
        self, snapshot: MarketSnapshot, marks: dict[str, float] | None = None
    ) -> PipelineResult:
        cfg = self._config
        inst = cfg.instruments.by_symbol(snapshot.symbol)
        now = snapshot.now or datetime.now(timezone.utc)
        marks = dict(marks or {})

        # 1. Technical analysis.
        ta = self._technical.analyze_full(
            symbol=snapshot.symbol,
            candles_1h=snapshot.candles_1h,
            candles_15m=snapshot.candles_15m,
        )
        if ta.entry_price is not None:
            marks.setdefault(snapshot.symbol, ta.entry_price)

        portfolio = self._portfolio_state(marks)
        portfolio_fit = (
            snapshot.portfolio_fit_score
            if snapshot.portfolio_fit_score is not None
            else self._portfolio_fit(snapshot.symbol, inst.bucket, portfolio)
        )

        # News/macro: use the News Macro Agent when configured, else the
        # static values carried by the snapshot.
        if self._news is not None:
            assessment = self._news.assess(
                bucket=inst.bucket,
                now=now,
                events=snapshot.macro_events,
                direction=ta.direction,
            )
            news_score = assessment.news_score
            news_conflict = assessment.block
        else:
            news_score = snapshot.news_score
            news_conflict = snapshot.news_conflict

        # 2. Decision.
        inputs = ScoreInputs(
            technical_score=ta.technical_score,
            trend_score=ta.trend_score,
            volume_score=ta.volume_score,
            news_score=news_score,
            sentiment_score=snapshot.sentiment_score,
            portfolio_fit_score=portfolio_fit,
            news_conflict=news_conflict,
            risk_rejected=False,  # the Risk Engine runs as its own stage below
        )
        decision = self._decision.decide(inputs)

        audit: dict[str, Any] = {
            "symbol": snapshot.symbol,
            "timestamp": now.isoformat(),
            "trend": ta.trend.value,
            "direction": ta.direction.value if ta.direction else None,
            "scores": {
                "technical": ta.technical_score,
                "trend": ta.trend_score,
                "volume": ta.volume_score,
                "news": news_score,
                "sentiment": snapshot.sentiment_score,
                "portfolio_fit": portfolio_fit,
                "final": decision.final_score,
            },
            "news_conflict": news_conflict,
            "decision": decision.outcome.value,
        }

        # Stop here unless we have an actionable candidate.
        if decision.outcome is not DecisionOutcome.TRADE_CANDIDATE:
            state = {
                DecisionOutcome.WAIT: PipelineState.WAIT,
                DecisionOutcome.WATCHLIST: PipelineState.WATCHLIST,
                DecisionOutcome.NO_TRADE: PipelineState.NO_TRADE,
            }[decision.outcome]
            self._write_audit(audit)
            return PipelineResult(
                symbol=snapshot.symbol,
                state=state,
                technical=ta,
                decision=decision,
                audit=audit,
            )

        # 3. Build the trade proposal from the technical signal.
        proposal = self._build_proposal(snapshot, ta, inst, now)
        audit["proposal"] = {
            "entry": proposal.entry_price,
            "stop_loss": proposal.stop_loss,
            "take_profit": proposal.take_profit,
            "reward_risk": proposal.reward_risk,
            "spread": proposal.spread,
            "data_age_seconds": proposal.data_age_seconds,
        }

        # Pre-trade audit write: if it fails, the trade must not proceed.
        audit_ok = True
        try:
            self._write_audit({**audit, "stage": "pre_trade"})
        except Exception:  # noqa: BLE001 - any failure blocks the trade
            audit_ok = False
        proposal = replace(proposal, audit_log_ok=audit_ok)

        # 4. Risk Engine.
        risk = self._risk.evaluate(proposal, portfolio)
        audit["risk"] = {
            "approved": risk.approved,
            "reasons": [r.value for r in risk.reasons],
            "size": risk.sizing.size if risk.sizing else None,
        }
        if not risk.approved:
            self._write_audit({**audit, "stage": "risk_rejected"})
            return PipelineResult(
                symbol=snapshot.symbol,
                state=PipelineState.RISK_REJECTED,
                technical=ta,
                decision=decision,
                risk=risk,
                proposal=proposal,
                audit=audit,
            )

        # 5. Execution — simulated only; read-only modes stop here.
        if self._mode in SIMULATED_MODES and self._simulator is not None:
            order = self._order_manager.submit(proposal, risk)
            audit["order"] = {"accepted": order.accepted, "detail": order.detail}
            self._write_audit({**audit, "stage": "executed"})
            return PipelineResult(
                symbol=snapshot.symbol,
                state=PipelineState.EXECUTED,
                technical=ta,
                decision=decision,
                risk=risk,
                order=order,
                proposal=proposal,
                audit=audit,
            )

        # Read-only modes: approved but intentionally not executed.
        audit["order"] = {"accepted": False, "detail": "read-only mode"}
        self._write_audit({**audit, "stage": "readonly_skipped"})
        logger.info("%s approved but not executed (read-only mode)", snapshot.symbol)
        return PipelineResult(
            symbol=snapshot.symbol,
            state=PipelineState.READONLY_SKIPPED,
            technical=ta,
            decision=decision,
            risk=risk,
            proposal=proposal,
            audit=audit,
        )

    # -- internals ---------------------------------------------------------

    def _build_proposal(
        self,
        snapshot: MarketSnapshot,
        ta: TechnicalSignal,
        inst: Any,
        now: datetime,
    ) -> TradeProposal:
        price = snapshot.price
        if snapshot.spread is not None:
            spread = snapshot.spread
        elif price is not None:
            spread = price.spread
        else:
            spread = 0.0
        if snapshot.data_age_seconds is not None:
            data_age = snapshot.data_age_seconds
        elif price is not None:
            data_age = price.age_seconds(now)
        else:
            data_age = 0.0

        assert ta.direction is not None and ta.entry_price is not None
        return TradeProposal(
            symbol=snapshot.symbol,
            bucket=inst.bucket,
            direction=ta.direction,
            entry_price=ta.entry_price,
            stop_loss=ta.stop_loss,
            take_profit=ta.take_profit,
            contract_size=inst.contract_size,
            margin_factor=inst.margin_factor,
            spread=spread,
            max_spread=inst.max_spread,
            data_age_seconds=data_age,
            has_conflicting_unconfirmed_news=snapshot.news_conflict,
            audit_log_ok=True,
        )

    def _portfolio_state(self, marks: dict[str, float]) -> PortfolioState:
        if self._simulator is not None:
            equity = self._simulator.equity(marks)
            available = self._simulator.available_margin(marks)
            positions = tuple(
                OpenPosition(
                    symbol=p.symbol,
                    bucket=self._bucket_of.get(p.symbol, "unknown"),
                    direction=p.direction,
                    size=p.size,
                )
                for p in self._simulator.open_positions
            )
        else:
            equity = self._starting_equity
            available = self._starting_equity
            positions = ()
        return PortfolioState(
            equity=equity,
            day_start_equity=self._day_start_equity,
            available_margin=available,
            open_positions=positions,
        )

    def _portfolio_fit(
        self, symbol: str, bucket: str, portfolio: PortfolioState
    ) -> float:
        """Simple portfolio-fit score: 1.0 if a new position fits, else 0.0."""

        cfg = self._config.risk
        if portfolio.open_count >= cfg.max_open_positions:
            return 0.0
        if portfolio.positions_in_bucket(bucket) >= cfg.max_positions_per_bucket:
            return 0.0
        return 1.0

    def _write_audit(self, record: dict[str, Any]) -> None:
        self._audit_sink(record)
