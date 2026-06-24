"""Typed inputs for the risk engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass(frozen=True)
class OpenPosition:
    """An open position as seen by the Portfolio Agent."""

    symbol: str
    bucket: str
    direction: Direction
    size: float
    # Optional richer metrics (populated from the simulator/account when known).
    notional: float = 0.0
    margin: float = 0.0

    @property
    def signed_notional(self) -> float:
        return self.notional if self.direction is Direction.LONG else -self.notional


@dataclass(frozen=True)
class PortfolioState:
    """Snapshot of the account/portfolio used for risk checks."""

    equity: float
    day_start_equity: float
    available_margin: float
    open_positions: tuple[OpenPosition, ...] = ()

    @property
    def open_count(self) -> int:
        return len(self.open_positions)

    @property
    def daily_pnl_fraction(self) -> float:
        """Signed daily PnL as a fraction of the day's starting equity.

        Negative means a loss. Returns 0.0 if the starting equity is unknown.
        """

        if self.day_start_equity <= 0:
            return 0.0
        return (self.equity - self.day_start_equity) / self.day_start_equity

    def positions_in_bucket(self, bucket: str) -> int:
        return sum(1 for p in self.open_positions if p.bucket == bucket)


@dataclass(frozen=True)
class TradeProposal:
    """A candidate trade submitted to the risk engine.

    Prices are in instrument quote-currency units. ``stop_loss`` is mandatory:
    a proposal without a stop loss is always rejected.
    """

    symbol: str
    bucket: str
    direction: Direction
    entry_price: float
    stop_loss: float | None
    take_profit: float | None
    contract_size: float = 1.0
    margin_factor: float = 0.05
    # Market quality signals provided by the Market Data Agent.
    spread: float = 0.0
    max_spread: float = 0.0
    data_age_seconds: float = 0.0
    # External gates evaluated upstream.
    has_conflicting_unconfirmed_news: bool = False
    audit_log_ok: bool = True
    # Optional explicit risk fraction; defaults to the policy default.
    risk_per_trade: float | None = None

    @property
    def stop_distance(self) -> float:
        if self.stop_loss is None:
            return 0.0
        return abs(self.entry_price - self.stop_loss)

    @property
    def reward_risk(self) -> float | None:
        if self.stop_loss is None or self.take_profit is None:
            return None
        risk = self.stop_distance
        if risk <= 0:
            return None
        reward = abs(self.take_profit - self.entry_price)
        return reward / risk
