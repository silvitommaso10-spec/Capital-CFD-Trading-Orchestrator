"""Portfolio Agent.

Responsible for equity, daily starting capital, PnL, open positions, exposure,
margin, used risk and correlations. It turns a :class:`PortfolioState` into a
portfolio assessment and a ``portfolio_fit_score`` used by the Decision Agent.

Analysis-only: it never places orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.config import RiskConfig
from risk.models import Direction, PortfolioState
from .base import BaseAgent, Signal


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


@dataclass(frozen=True)
class PortfolioAssessment:
    equity: float
    day_start_equity: float
    daily_pnl_fraction: float
    num_positions: int
    max_positions: int
    positions_by_bucket: dict[str, int]
    gross_exposure: float
    net_exposure: float
    used_margin: float
    margin_utilization: float
    portfolio_fit_score: float
    correlated_bucket_in_use: bool


class PortfolioAgent(BaseAgent):
    """Compute portfolio exposure, used margin and a fit score."""

    name = "portfolio"

    def __init__(self, config: RiskConfig) -> None:
        self._cfg = config

    # -- exposure / margin -------------------------------------------------

    def used_margin(self, portfolio: PortfolioState) -> float:
        explicit = sum(p.margin for p in portfolio.open_positions)
        if explicit > 0:
            return explicit
        # Fall back to equity minus available margin.
        return max(0.0, portfolio.equity - portfolio.available_margin)

    def gross_exposure(self, portfolio: PortfolioState) -> float:
        return sum(p.notional for p in portfolio.open_positions)

    def net_exposure(self, portfolio: PortfolioState) -> float:
        return sum(p.signed_notional for p in portfolio.open_positions)

    # -- fit score ---------------------------------------------------------

    def portfolio_fit(
        self, bucket: str | None, portfolio: PortfolioState
    ) -> float:
        """Continuous fit score in ``[0, 1]`` for adding a position.

        Returns ``0.0`` if a hard limit (max open positions or per-bucket limit)
        would be breached. Otherwise blends free-slot headroom with margin
        headroom.
        """

        cfg = self._cfg
        if portfolio.open_count >= cfg.max_open_positions:
            return 0.0
        if (
            bucket is not None
            and portfolio.positions_in_bucket(bucket) >= cfg.max_positions_per_bucket
        ):
            return 0.0

        position_headroom = (
            (cfg.max_open_positions - portfolio.open_count) / cfg.max_open_positions
            if cfg.max_open_positions > 0
            else 0.0
        )
        margin_headroom = _clamp(1.0 - self._margin_utilization(portfolio))
        return _clamp(0.5 * position_headroom + 0.5 * margin_headroom)

    def _margin_utilization(self, portfolio: PortfolioState) -> float:
        if portfolio.equity <= 0:
            return 1.0
        return self.used_margin(portfolio) / portfolio.equity

    # -- assessment --------------------------------------------------------

    def assess(
        self, portfolio: PortfolioState, proposed_bucket: str | None = None
    ) -> PortfolioAssessment:
        by_bucket: dict[str, int] = {}
        for p in portfolio.open_positions:
            by_bucket[p.bucket] = by_bucket.get(p.bucket, 0) + 1

        correlated = (
            proposed_bucket is not None and by_bucket.get(proposed_bucket, 0) > 0
        )
        return PortfolioAssessment(
            equity=portfolio.equity,
            day_start_equity=portfolio.day_start_equity,
            daily_pnl_fraction=portfolio.daily_pnl_fraction,
            num_positions=portfolio.open_count,
            max_positions=self._cfg.max_open_positions,
            positions_by_bucket=by_bucket,
            gross_exposure=self.gross_exposure(portfolio),
            net_exposure=self.net_exposure(portfolio),
            used_margin=self.used_margin(portfolio),
            margin_utilization=self._margin_utilization(portfolio),
            portfolio_fit_score=self.portfolio_fit(proposed_bucket, portfolio),
            correlated_bucket_in_use=correlated,
        )

    # -- BaseAgent ---------------------------------------------------------

    def analyze(self, context: dict[str, Any]) -> Signal:
        """Return a Signal carrying the portfolio-fit score.

        ``context`` must contain ``portfolio`` (a :class:`PortfolioState`) and may
        contain ``bucket``.
        """

        portfolio: PortfolioState = context["portfolio"]
        bucket = context.get("bucket")
        fit = self.portfolio_fit(bucket, portfolio)
        return Signal(
            self.name,
            fit,
            f"fit={fit:.2f}",
            metadata={
                "num_positions": portfolio.open_count,
                "margin_utilization": self._margin_utilization(portfolio),
            },
        )
