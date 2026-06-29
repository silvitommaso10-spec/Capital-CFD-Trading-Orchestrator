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


def test_to_dict_from_dict_round_trip() -> None:
    sim = PaperCFDSimulator(starting_balance=10_000.0, spread=0.5)
    sim.open_position(
        symbol="US500", direction=Direction.LONG, size=2.0, price=5000.0,
        contract_size=1.0, margin_factor=0.05, stop_loss=4950.0,
        take_profit=5100.0,
    )
    sim.open_position(
        symbol="GOLD", direction=Direction.SHORT, size=3.0, price=2000.0,
        margin_factor=0.05,
    )
    closed = sim.open_position(
        symbol="USOIL", direction=Direction.LONG, size=1.0, price=75.0,
    )
    sim.close_position(closed.position_id, 80.0)  # realize some PnL

    restored = PaperCFDSimulator.from_dict(sim.to_dict())

    assert math.isclose(restored.starting_balance, sim.starting_balance)
    assert math.isclose(restored.spread, sim.spread)
    assert math.isclose(restored.realized_pnl, sim.realized_pnl)
    assert len(restored.open_positions) == 2
    marks = {"US500": 5010.0, "GOLD": 1990.0}
    assert math.isclose(restored.equity(marks), sim.equity(marks))
    # the id counter continues without colliding with restored positions
    new_pos = restored.open_position(
        symbol="BTC", direction=Direction.LONG, size=1.0, price=60000.0,
    )
    existing_ids = {p.position_id for p in sim.open_positions}
    assert new_pos.position_id not in existing_ids
