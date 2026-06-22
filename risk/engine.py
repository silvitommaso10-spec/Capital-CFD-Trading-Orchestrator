"""The deterministic Risk Engine.

Given a :class:`TradeProposal`, a :class:`PortfolioState` and the loaded
:class:`RiskConfig`, the engine returns an approve/reject decision. It is the
single authority that decides whether a trade may proceed. The decision is
fully deterministic and all failed checks are reported (no short-circuit), so
the audit log captures every reason a trade was blocked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.config import RiskConfig
from .margin import MarginCalculator, PositionSizing
from .models import PortfolioState, TradeProposal


class RejectionReason(str, Enum):
    AUDIT_LOG_UNAVAILABLE = "audit_log_unavailable"
    MISSING_STOP_LOSS = "missing_stop_loss"
    EMERGENCY_KILL_SWITCH = "emergency_kill_switch"
    DAILY_HARD_STOP = "daily_hard_stop"
    STALE_DATA = "stale_data"
    HIGH_SPREAD = "high_spread"
    CONFLICTING_NEWS = "conflicting_unconfirmed_news"
    MAX_OPEN_POSITIONS = "max_open_positions"
    BUCKET_LIMIT = "bucket_limit"
    REWARD_RISK_TOO_LOW = "reward_risk_too_low"
    INSUFFICIENT_MARGIN = "insufficient_margin"
    SIZE_TOO_SMALL = "size_too_small"
    INVALID_PROPOSAL = "invalid_proposal"


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reasons: tuple[RejectionReason, ...] = ()
    sizing: PositionSizing | None = None
    risk_fraction_used: float = 0.0
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def rejected(self) -> bool:
        return not self.approved


class RiskEngine:
    """Deterministic trade approval."""

    def __init__(
        self, config: RiskConfig, margin_calculator: MarginCalculator | None = None
    ) -> None:
        self._config = config
        self._margin = margin_calculator or MarginCalculator()

    def evaluate(
        self, proposal: TradeProposal, portfolio: PortfolioState
    ) -> RiskDecision:
        cfg = self._config
        reasons: list[RejectionReason] = []
        warnings: list[str] = []

        # 1. Audit log must be writable before anything else.
        if cfg.block_if_audit_log_fails and not proposal.audit_log_ok:
            reasons.append(RejectionReason.AUDIT_LOG_UNAVAILABLE)

        # 2. Stop loss is mandatory.
        if cfg.require_stop_loss and proposal.stop_loss is None:
            reasons.append(RejectionReason.MISSING_STOP_LOSS)

        # 3/4. Daily loss controls (daily_pnl_fraction is negative on a loss).
        pnl = portfolio.daily_pnl_fraction
        if pnl <= -cfg.emergency_kill_switch:
            reasons.append(RejectionReason.EMERGENCY_KILL_SWITCH)
        elif pnl <= -cfg.daily_hard_stop:
            reasons.append(RejectionReason.DAILY_HARD_STOP)

        # Soft stop reduces risk-on exposure rather than blocking outright.
        risk_fraction = proposal.risk_per_trade or cfg.default_risk_per_trade
        risk_fraction = min(risk_fraction, cfg.max_risk_per_trade)
        if pnl <= -cfg.daily_soft_stop:
            risk_fraction = min(risk_fraction, cfg.max_risk_per_trade) / 2.0
            warnings.append("daily_soft_stop_active: risk per trade halved")

        # 5. Data freshness.
        if cfg.block_on_stale_data and proposal.data_age_seconds > cfg.max_data_age_seconds:
            reasons.append(RejectionReason.STALE_DATA)

        # 6. Spread.
        if (
            cfg.block_on_high_spread
            and proposal.max_spread > 0
            and proposal.spread > proposal.max_spread
        ):
            reasons.append(RejectionReason.HIGH_SPREAD)

        # 7. Conflicting unconfirmed news.
        if (
            cfg.block_on_unconfirmed_conflicting_news
            and proposal.has_conflicting_unconfirmed_news
        ):
            reasons.append(RejectionReason.CONFLICTING_NEWS)

        # 8/9. Concurrency limits.
        if portfolio.open_count >= cfg.max_open_positions:
            reasons.append(RejectionReason.MAX_OPEN_POSITIONS)
        if portfolio.positions_in_bucket(proposal.bucket) >= cfg.max_positions_per_bucket:
            reasons.append(RejectionReason.BUCKET_LIMIT)

        # 10. Reward / risk ratio.
        rr = proposal.reward_risk
        if rr is None or rr < cfg.min_reward_risk:
            reasons.append(RejectionReason.REWARD_RISK_TOO_LOW)

        # 11/12/13. Sizing + margin (only attempted with a usable stop).
        sizing: PositionSizing | None = None
        if proposal.stop_loss is not None and proposal.stop_distance > 0:
            try:
                sizing = self._margin.size_for_risk(
                    equity=portfolio.equity,
                    risk_per_trade=risk_fraction,
                    entry_price=proposal.entry_price,
                    stop_loss=proposal.stop_loss,
                    contract_size=proposal.contract_size,
                    margin_factor=proposal.margin_factor,
                )
            except ValueError:
                reasons.append(RejectionReason.INVALID_PROPOSAL)

        if sizing is not None:
            if sizing.size <= 0:
                reasons.append(RejectionReason.SIZE_TOO_SMALL)
            elif (
                cfg.block_on_insufficient_margin
                and sizing.required_margin > portfolio.available_margin
            ):
                reasons.append(RejectionReason.INSUFFICIENT_MARGIN)

        approved = not reasons
        return RiskDecision(
            approved=approved,
            reasons=tuple(reasons),
            sizing=sizing if approved else (sizing if sizing else None),
            risk_fraction_used=risk_fraction if approved else 0.0,
            warnings=tuple(warnings),
        )
