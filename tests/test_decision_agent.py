"""Tests for the Decision Agent scoring and decision rules."""

from __future__ import annotations

import pytest

from agents.decision_agent import (
    WEIGHTS,
    Decision,
    DecisionAgent,
    DecisionOutcome,
    ScoreInputs,
)


def test_weights_sum_to_one() -> None:
    assert pytest.approx(sum(WEIGHTS.values())) == 1.0


def uniform_inputs(value: float, **overrides: object) -> ScoreInputs:
    base = dict(
        technical_score=value,
        trend_score=value,
        volume_score=value,
        news_score=value,
        sentiment_score=value,
        portfolio_fit_score=value,
    )
    base.update(overrides)
    return ScoreInputs(**base)  # type: ignore[arg-type]


def test_final_score_uses_weighted_sum() -> None:
    agent = DecisionAgent()
    inputs = ScoreInputs(
        technical_score=0.8,
        trend_score=0.7,
        volume_score=0.6,
        news_score=0.5,
        sentiment_score=1.0,
        portfolio_fit_score=0.4,
    )
    expected = (
        0.8 * 0.40 + 0.7 * 0.20 + 0.6 * 0.15 + 0.5 * 0.15 + 1.0 * 0.05 + 0.4 * 0.05
    )
    assert agent.final_score(inputs) == pytest.approx(expected)


def test_trade_candidate_threshold() -> None:
    agent = DecisionAgent()
    # uniform 0.8 -> final score 0.8 >= 0.72
    decision = agent.decide(uniform_inputs(0.8))
    assert decision.outcome is DecisionOutcome.TRADE_CANDIDATE


def test_watchlist_band() -> None:
    agent = DecisionAgent()
    # uniform 0.65 -> 0.65 in [0.60, 0.72)
    decision = agent.decide(uniform_inputs(0.65))
    assert decision.outcome is DecisionOutcome.WATCHLIST


def test_no_trade_below_band() -> None:
    agent = DecisionAgent()
    decision = agent.decide(uniform_inputs(0.5))
    assert decision.outcome is DecisionOutcome.NO_TRADE


def test_news_conflict_forces_wait() -> None:
    agent = DecisionAgent()
    # high score but news conflict -> WAIT
    decision = agent.decide(uniform_inputs(0.9, news_conflict=True))
    assert decision.outcome is DecisionOutcome.WAIT


def test_risk_rejection_forces_no_trade() -> None:
    agent = DecisionAgent()
    decision = agent.decide(uniform_inputs(0.9, risk_rejected=True))
    assert decision.outcome is DecisionOutcome.NO_TRADE


def test_scores_are_clamped() -> None:
    agent = DecisionAgent()
    # out-of-range inputs are clamped to [0, 1]
    decision = agent.decide(uniform_inputs(5.0))
    assert decision.final_score == pytest.approx(1.0)
    assert isinstance(decision, Decision)
