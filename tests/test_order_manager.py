"""Tests for the Order Manager safety invariants."""

from __future__ import annotations

import pytest

from app.errors import LiveTradingDisabledError, RiskRejectedError
from app.modes import OperatingMode
from backtesting.paper_simulator import PaperCFDSimulator
from execution.order_manager import OrderManager
from risk.engine import RejectionReason, RiskDecision
from risk.margin import PositionSizing
from risk.models import Direction, TradeProposal


def proposal() -> TradeProposal:
    return TradeProposal(
        symbol="US500",
        bucket="equity_indices",
        direction=Direction.LONG,
        entry_price=5000.0,
        stop_loss=4990.0,
        take_profit=5020.0,
    )


def approved_decision() -> RiskDecision:
    sizing = PositionSizing(
        size=2.0, risk_amount=20.0, notional=10000.0,
        required_margin=500.0, stop_distance=10.0,
    )
    return RiskDecision(approved=True, sizing=sizing, risk_fraction_used=0.0075)


def test_rejects_unapproved_trade() -> None:
    manager = OrderManager(OperatingMode.SHADOW, PaperCFDSimulator(10_000.0))
    decision = RiskDecision(approved=False, reasons=(RejectionReason.HIGH_SPREAD,))
    with pytest.raises(RiskRejectedError):
        manager.submit(proposal(), decision)


def test_shadow_mode_routes_to_simulator() -> None:
    sim = PaperCFDSimulator(starting_balance=10_000.0)
    manager = OrderManager(OperatingMode.SHADOW, sim)
    result = manager.submit(proposal(), approved_decision())
    assert result.accepted
    assert result.simulated_position is not None
    assert len(sim.open_positions) == 1


def test_capital_demo_mode_is_read_only() -> None:
    manager = OrderManager(OperatingMode.CAPITAL_DEMO)
    with pytest.raises(LiveTradingDisabledError):
        manager.submit(proposal(), approved_decision())


def test_live_disabled_mode_cannot_trade() -> None:
    manager = OrderManager(OperatingMode.LIVE_DISABLED)
    with pytest.raises(LiveTradingDisabledError):
        manager.submit(proposal(), approved_decision())
