"""Tests for the paper CFD simulator."""

from __future__ import annotations

import math

from backtesting.paper_simulator import PaperCFDSimulator
from risk.models import Direction


def test_open_long_and_unrealized_pnl() -> None:
    sim = PaperCFDSimulator(starting_balance=10_000.0)
    pos = sim.open_position(
        symbol="US500", direction=Direction.LONG, size=2.0, price=5000.0,
        margin_factor=0.05,
    )
    assert pos.entry_price == 5000.0
    assert math.isclose(pos.margin, 2.0 * 5000.0 * 0.05)
    # price up 10 -> +20 for size 2
    assert math.isclose(pos.unrealized_pnl(5010.0), 20.0)
    assert math.isclose(sim.equity({"US500": 5010.0}), 10_020.0)


def test_short_pnl_inverts() -> None:
    sim = PaperCFDSimulator(starting_balance=10_000.0)
    pos = sim.open_position(
        symbol="GOLD", direction=Direction.SHORT, size=1.0, price=2000.0,
    )
    # price down 5 -> +5 for a short
    assert math.isclose(pos.unrealized_pnl(1995.0), 5.0)
    assert math.isclose(pos.unrealized_pnl(2005.0), -5.0)


def test_spread_applied_on_fill_and_exit() -> None:
    sim = PaperCFDSimulator(starting_balance=10_000.0, spread=2.0)
    pos = sim.open_position(
        symbol="US500", direction=Direction.LONG, size=1.0, price=5000.0,
    )
    # long fills at price + half spread
    assert pos.entry_price == 5001.0
    # closing a long at 5001 exits at 5000 (minus half spread) -> -1 PnL
    pnl = sim.close_position(pos.position_id, 5001.0)
    assert math.isclose(pnl, -1.0)
    assert math.isclose(sim.realized_pnl, -1.0)


def test_close_realizes_pnl_and_frees_margin() -> None:
    sim = PaperCFDSimulator(starting_balance=10_000.0)
    pos = sim.open_position(
        symbol="US500", direction=Direction.LONG, size=1.0, price=5000.0,
        margin_factor=0.05,
    )
    assert sim.used_margin() > 0
    pnl = sim.close_position(pos.position_id, 5100.0)
    assert math.isclose(pnl, 100.0)
    assert sim.used_margin() == 0.0
    assert sim.open_positions == ()
    assert math.isclose(sim.equity({}), 10_100.0)
