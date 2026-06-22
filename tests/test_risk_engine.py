"""Tests for the deterministic Risk Engine."""

from __future__ import annotations

import pytest

from app.config import RiskConfig
from risk.engine import RejectionReason, RiskEngine
from risk.models import Direction, OpenPosition, PortfolioState, TradeProposal


def make_config(**overrides: object) -> RiskConfig:
    base = dict(
        default_risk_per_trade=0.0075,
        max_risk_per_trade=0.01,
        daily_soft_stop=0.03,
        daily_hard_stop=0.05,
        emergency_kill_switch=0.10,
        max_open_positions=3,
        max_positions_per_bucket=1,
        min_reward_risk=1.8,
        require_stop_loss=True,
        block_on_stale_data=True,
        block_on_high_spread=True,
        block_on_insufficient_margin=True,
        block_on_unconfirmed_conflicting_news=True,
        block_if_audit_log_fails=True,
        max_data_age_seconds=30.0,
        max_spread={"equity_indices": 1.5},
    )
    base.update(overrides)
    return RiskConfig(**base)  # type: ignore[arg-type]


def good_proposal(**overrides: object) -> TradeProposal:
    base = dict(
        symbol="US500",
        bucket="equity_indices",
        direction=Direction.LONG,
        entry_price=5000.0,
        stop_loss=4990.0,        # distance 10
        take_profit=5020.0,      # reward 20 -> rr 2.0
        contract_size=1.0,
        margin_factor=0.05,
        spread=0.5,
        max_spread=1.5,
        data_age_seconds=2.0,
        has_conflicting_unconfirmed_news=False,
        audit_log_ok=True,
    )
    base.update(overrides)
    return TradeProposal(**base)  # type: ignore[arg-type]


def good_portfolio(**overrides: object) -> PortfolioState:
    base = dict(
        equity=10_000.0,
        day_start_equity=10_000.0,
        available_margin=5_000.0,
        open_positions=(),
    )
    base.update(overrides)
    return PortfolioState(**base)  # type: ignore[arg-type]


def test_approves_well_formed_trade() -> None:
    engine = RiskEngine(make_config())
    decision = engine.evaluate(good_proposal(), good_portfolio())
    assert decision.approved
    assert decision.reasons == ()
    assert decision.sizing is not None
    assert decision.sizing.size == pytest.approx(7.5)
    assert decision.risk_fraction_used == pytest.approx(0.0075)


def test_missing_stop_loss_rejected() -> None:
    engine = RiskEngine(make_config())
    decision = engine.evaluate(
        good_proposal(stop_loss=None, take_profit=None), good_portfolio()
    )
    assert decision.rejected
    assert RejectionReason.MISSING_STOP_LOSS in decision.reasons


def test_low_reward_risk_rejected() -> None:
    engine = RiskEngine(make_config())
    # reward 10 vs risk 10 -> rr 1.0 < 1.8
    decision = engine.evaluate(good_proposal(take_profit=5010.0), good_portfolio())
    assert decision.rejected
    assert RejectionReason.REWARD_RISK_TOO_LOW in decision.reasons


def test_stale_data_rejected() -> None:
    engine = RiskEngine(make_config())
    decision = engine.evaluate(good_proposal(data_age_seconds=120.0), good_portfolio())
    assert RejectionReason.STALE_DATA in decision.reasons


def test_high_spread_rejected() -> None:
    engine = RiskEngine(make_config())
    decision = engine.evaluate(good_proposal(spread=3.0), good_portfolio())
    assert RejectionReason.HIGH_SPREAD in decision.reasons


def test_conflicting_news_rejected() -> None:
    engine = RiskEngine(make_config())
    decision = engine.evaluate(
        good_proposal(has_conflicting_unconfirmed_news=True), good_portfolio()
    )
    assert RejectionReason.CONFLICTING_NEWS in decision.reasons


def test_audit_log_failure_rejected() -> None:
    engine = RiskEngine(make_config())
    decision = engine.evaluate(good_proposal(audit_log_ok=False), good_portfolio())
    assert RejectionReason.AUDIT_LOG_UNAVAILABLE in decision.reasons


def test_max_open_positions_rejected() -> None:
    engine = RiskEngine(make_config())
    positions = tuple(
        OpenPosition(f"S{i}", f"b{i}", Direction.LONG, 1.0) for i in range(3)
    )
    decision = engine.evaluate(good_proposal(), good_portfolio(open_positions=positions))
    assert RejectionReason.MAX_OPEN_POSITIONS in decision.reasons


def test_bucket_limit_rejected() -> None:
    engine = RiskEngine(make_config())
    positions = (OpenPosition("NASDAQ", "equity_indices", Direction.LONG, 1.0),)
    decision = engine.evaluate(good_proposal(), good_portfolio(open_positions=positions))
    assert RejectionReason.BUCKET_LIMIT in decision.reasons


def test_insufficient_margin_rejected() -> None:
    engine = RiskEngine(make_config())
    # required margin = 7.5 * 5000 * 0.05 = 1875; make available smaller
    decision = engine.evaluate(good_proposal(), good_portfolio(available_margin=100.0))
    assert RejectionReason.INSUFFICIENT_MARGIN in decision.reasons


def test_kill_switch_rejected() -> None:
    engine = RiskEngine(make_config())
    portfolio = good_portfolio(equity=8_900.0, day_start_equity=10_000.0)  # -11%
    decision = engine.evaluate(good_proposal(), portfolio)
    assert RejectionReason.EMERGENCY_KILL_SWITCH in decision.reasons


def test_hard_stop_rejected() -> None:
    engine = RiskEngine(make_config())
    portfolio = good_portfolio(equity=9_400.0, day_start_equity=10_000.0)  # -6%
    decision = engine.evaluate(good_proposal(), portfolio)
    assert RejectionReason.DAILY_HARD_STOP in decision.reasons


def test_soft_stop_halves_risk_but_can_approve() -> None:
    engine = RiskEngine(make_config())
    portfolio = good_portfolio(equity=9_650.0, day_start_equity=10_000.0)  # -3.5%
    decision = engine.evaluate(good_proposal(), portfolio)
    assert decision.approved
    assert decision.risk_fraction_used == pytest.approx(0.0075 / 2.0)
    assert any("soft_stop" in w for w in decision.warnings)


def test_decision_is_deterministic() -> None:
    engine = RiskEngine(make_config())
    p, pf = good_proposal(), good_portfolio()
    assert engine.evaluate(p, pf) == engine.evaluate(p, pf)
