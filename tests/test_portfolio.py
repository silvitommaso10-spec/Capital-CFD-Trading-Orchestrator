"""Tests for the Portfolio Agent."""

from __future__ import annotations

import pytest

from agents.portfolio import PortfolioAgent
from app.config import load_config
from risk.models import Direction, OpenPosition, PortfolioState


def agent() -> PortfolioAgent:
    return PortfolioAgent(load_config().risk)


def position(symbol: str, bucket: str, *, size: float = 1.0, notional: float = 1000.0,
             margin: float = 50.0, direction: Direction = Direction.LONG) -> OpenPosition:
    return OpenPosition(symbol, bucket, direction, size, notional=notional, margin=margin)


def test_fit_is_one_when_flat() -> None:
    a = agent()
    pf = PortfolioState(equity=10_000.0, day_start_equity=10_000.0,
                        available_margin=10_000.0)
    assert a.portfolio_fit("equity_indices", pf) == 1.0


def test_fit_zero_when_bucket_limit_reached() -> None:
    a = agent()
    pf = PortfolioState(
        equity=10_000.0, day_start_equity=10_000.0, available_margin=9_000.0,
        open_positions=(position("US500", "equity_indices"),),
    )
    # equity_indices already has a position; max per bucket is 1
    assert a.portfolio_fit("equity_indices", pf) == 0.0
    # a different bucket still fits (but < 1.0 because a slot/margin is used)
    assert 0.0 < a.portfolio_fit("metals", pf) < 1.0


def test_fit_zero_when_max_positions_reached() -> None:
    a = agent()
    positions = (
        position("US500", "equity_indices"),
        position("GOLD", "metals"),
        position("USOIL", "energy"),
    )
    pf = PortfolioState(10_000.0, 10_000.0, 8_000.0, positions)
    assert a.portfolio_fit("crypto", pf) == 0.0


def test_exposure_metrics() -> None:
    a = agent()
    positions = (
        position("US500", "equity_indices", notional=2000.0, margin=100.0,
                 direction=Direction.LONG),
        position("GOLD", "metals", notional=500.0, margin=25.0,
                 direction=Direction.SHORT),
    )
    pf = PortfolioState(10_000.0, 10_000.0, 9_875.0, positions)
    assert a.gross_exposure(pf) == 2500.0
    assert a.net_exposure(pf) == 1500.0  # 2000 long - 500 short
    assert a.used_margin(pf) == 125.0


def test_assess_reports_buckets_and_daily_pnl() -> None:
    a = agent()
    positions = (position("US500", "equity_indices"),)
    pf = PortfolioState(equity=9_700.0, day_start_equity=10_000.0,
                        available_margin=9_650.0, open_positions=positions)
    result = a.assess(pf, proposed_bucket="equity_indices")
    assert result.num_positions == 1
    assert result.positions_by_bucket == {"equity_indices": 1}
    assert result.correlated_bucket_in_use is True
    assert result.daily_pnl_fraction == pytest.approx(-0.03)
    assert result.portfolio_fit_score == 0.0  # same bucket -> blocked


def test_analyze_returns_signal() -> None:
    a = agent()
    pf = PortfolioState(10_000.0, 10_000.0, 10_000.0)
    signal = a.analyze({"portfolio": pf, "bucket": "crypto"})
    assert signal.name == "portfolio"
    assert signal.score == 1.0
