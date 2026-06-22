"""Tests for the margin / position-sizing calculator."""

from __future__ import annotations

import math

import pytest

from risk.margin import MarginCalculator


def test_size_for_risk_matches_risk_budget() -> None:
    calc = MarginCalculator()
    sizing = calc.size_for_risk(
        equity=10_000.0,
        risk_per_trade=0.0075,  # 0.75% -> 75.0
        entry_price=5000.0,
        stop_loss=4990.0,       # stop distance = 10
        contract_size=1.0,
        margin_factor=0.05,
    )
    # 75 / (10 * 1) = 7.5 contracts
    assert math.isclose(sizing.size, 7.5, rel_tol=1e-9)
    assert math.isclose(sizing.risk_amount, 75.0, rel_tol=1e-9)
    assert math.isclose(sizing.notional, 7.5 * 5000.0, rel_tol=1e-9)
    assert math.isclose(sizing.required_margin, 7.5 * 5000.0 * 0.05, rel_tol=1e-9)


def test_min_deal_size_snaps_down() -> None:
    calc = MarginCalculator()
    sizing = calc.size_for_risk(
        equity=10_000.0,
        risk_per_trade=0.0075,
        entry_price=5000.0,
        stop_loss=4990.0,
        min_deal_size=1.0,  # snap 7.5 -> 7.0
    )
    assert sizing.size == 7.0
    # risk recomputed against the snapped size
    assert math.isclose(sizing.risk_amount, 70.0, rel_tol=1e-9)


def test_effective_leverage() -> None:
    calc = MarginCalculator()
    sizing = calc.size_for_risk(
        equity=10_000.0,
        risk_per_trade=0.01,
        entry_price=100.0,
        stop_loss=99.0,
        margin_factor=0.05,
    )
    # leverage = notional / margin = 1 / margin_factor = 20
    assert math.isclose(sizing.effective_leverage, 20.0, rel_tol=1e-9)


def test_zero_stop_distance_rejected() -> None:
    calc = MarginCalculator()
    with pytest.raises(ValueError):
        calc.size_for_risk(
            equity=10_000.0,
            risk_per_trade=0.01,
            entry_price=100.0,
            stop_loss=100.0,
        )


def test_non_positive_equity_rejected() -> None:
    calc = MarginCalculator()
    with pytest.raises(ValueError):
        calc.size_for_risk(
            equity=0.0,
            risk_per_trade=0.01,
            entry_price=100.0,
            stop_loss=99.0,
        )
