"""Paper CFD simulator.

A self-contained simulator for CFD positions used by BACKTEST and SHADOW
modes. It models fills with a configurable spread/slippage, tracks margin and
realized/unrealized PnL, and never touches the broker.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from risk.models import Direction


@dataclass
class SimulatedPosition:
    position_id: int
    symbol: str
    direction: Direction
    size: float
    entry_price: float
    contract_size: float
    margin_factor: float
    stop_loss: float | None = None
    take_profit: float | None = None

    @property
    def notional(self) -> float:
        return self.size * self.entry_price * self.contract_size

    @property
    def margin(self) -> float:
        return self.notional * self.margin_factor

    def unrealized_pnl(self, price: float) -> float:
        diff = price - self.entry_price
        if self.direction is Direction.SHORT:
            diff = -diff
        return diff * self.size * self.contract_size

    def to_dict(self) -> dict[str, Any]:
        return {
            "position_id": self.position_id,
            "symbol": self.symbol,
            "direction": self.direction.value,
            "size": self.size,
            "entry_price": self.entry_price,
            "contract_size": self.contract_size,
            "margin_factor": self.margin_factor,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SimulatedPosition":
        return cls(
            position_id=int(data["position_id"]),
            symbol=str(data["symbol"]),
            direction=Direction(data["direction"]),
            size=float(data["size"]),
            entry_price=float(data["entry_price"]),
            contract_size=float(data["contract_size"]),
            margin_factor=float(data["margin_factor"]),
            stop_loss=data.get("stop_loss"),
            take_profit=data.get("take_profit"),
        )


@dataclass
class PaperCFDSimulator:
    """Simulates CFD trading on a paper account."""

    starting_balance: float
    spread: float = 0.0
    realized_pnl: float = 0.0
    _positions: dict[int, SimulatedPosition] = field(default_factory=dict)
    _next_id: int = 1

    @property
    def open_positions(self) -> tuple[SimulatedPosition, ...]:
        return tuple(self._positions.values())

    def used_margin(self) -> float:
        return sum(p.margin for p in self._positions.values())

    def equity(self, marks: dict[str, float]) -> float:
        """Account equity given current ``marks`` (symbol -> price)."""

        unrealized = sum(
            p.unrealized_pnl(marks.get(p.symbol, p.entry_price))
            for p in self._positions.values()
        )
        return self.starting_balance + self.realized_pnl + unrealized

    def available_margin(self, marks: dict[str, float]) -> float:
        return self.equity(marks) - self.used_margin()

    def open_position(
        self,
        *,
        symbol: str,
        direction: Direction,
        size: float,
        price: float,
        contract_size: float = 1.0,
        margin_factor: float = 0.05,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> SimulatedPosition:
        """Open a simulated position. Fill price includes half the spread."""

        if size <= 0:
            raise ValueError("size must be positive")
        half_spread = self.spread / 2.0
        fill = price + half_spread if direction is Direction.LONG else price - half_spread
        position_id = self._next_id
        self._next_id += 1
        position = SimulatedPosition(
            position_id=position_id,
            symbol=symbol,
            direction=direction,
            size=size,
            entry_price=fill,
            contract_size=contract_size,
            margin_factor=margin_factor,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        self._positions[position.position_id] = position
        return position

    def close_position(self, position_id: int, price: float) -> float:
        """Close a position at ``price`` (minus half spread). Returns realized PnL."""

        position = self._positions.pop(position_id)
        half_spread = self.spread / 2.0
        exit_price = (
            price - half_spread
            if position.direction is Direction.LONG
            else price + half_spread
        )
        pnl = position.unrealized_pnl(exit_price)
        self.realized_pnl += pnl
        return pnl

    # -- persistence -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialise the full account state (JSON-friendly)."""

        return {
            "starting_balance": self.starting_balance,
            "spread": self.spread,
            "realized_pnl": self.realized_pnl,
            "next_id": self._next_id,
            "positions": [p.to_dict() for p in self._positions.values()],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PaperCFDSimulator":
        """Reconstruct a simulator from :meth:`to_dict` output."""

        sim = cls(
            starting_balance=float(data["starting_balance"]),
            spread=float(data.get("spread", 0.0)),
            realized_pnl=float(data.get("realized_pnl", 0.0)),
        )
        positions = [
            SimulatedPosition.from_dict(p) for p in data.get("positions", [])
        ]
        sim._positions = {p.position_id: p for p in positions}
        sim._next_id = int(
            data.get("next_id", max((p.position_id for p in positions), default=0) + 1)
        )
        return sim
