"""Tests for the Social Sentiment Agent (a weak signal)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agents.candles import Candle
from agents.decision_agent import DecisionAgent, DecisionOutcome, ScoreInputs
from agents.social_sentiment import SentimentSample, SocialSentimentAgent
from app.config import load_config
from app.modes import OperatingMode
from app.orchestrator import MarketSnapshot, Orchestrator, PipelineState
from backtesting.paper_simulator import PaperCFDSimulator
from capital.models import Price

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def agent() -> SocialSentimentAgent:
    return SocialSentimentAgent()


def samples(value: float, n: int = 5) -> list[SentimentSample]:
    return [SentimentSample(NOW - timedelta(minutes=i * 5), value) for i in range(n)]


def test_no_samples_is_neutral() -> None:
    assert agent().assess("crypto", NOW, []).score == 0.5


def test_bullish_sentiment_raises_score_for_crypto() -> None:
    a = agent()
    result = a.assess("crypto", NOW, samples(1.0))
    assert result.score > 0.5
    assert result.raw_sentiment == 1.0
    assert result.relevance == 1.0


def test_bearish_sentiment_lowers_score() -> None:
    assert agent().assess("crypto", NOW, samples(-1.0)).score < 0.5


def test_non_crypto_buckets_are_damped() -> None:
    a = agent()
    crypto = a.assess("crypto", NOW, samples(1.0)).score
    equities = a.assess("equity_indices", NOW, samples(1.0)).score
    # same raw sentiment moves crypto more than equities
    assert (crypto - 0.5) > (equities - 0.5) > 0.0


def test_weighted_mean_used() -> None:
    a = agent()
    s = [
        SentimentSample(NOW, 1.0, weight=3.0),
        SentimentSample(NOW, -1.0, weight=1.0),
    ]
    # weighted raw = (3 - 1) / 4 = 0.5
    assert abs(a.assess("crypto", NOW, s).raw_sentiment - 0.5) < 1e-9


def test_old_samples_ignored() -> None:
    a = agent()
    old = [SentimentSample(NOW - timedelta(hours=5), 1.0)]  # beyond 180m lookback
    assert a.assess("crypto", NOW, old).score == 0.5


def test_analyze_marks_signal_weak() -> None:
    signal = agent().analyze({"bucket": "crypto", "now": NOW, "samples": samples(0.8)})
    assert signal.name == "social_sentiment"
    assert signal.metadata["is_weak"] is True


# -- structural constraint: sentiment cannot open a trade alone -----------


def test_sentiment_alone_cannot_create_a_candidate() -> None:
    decider = DecisionAgent()
    # Everything neutral/zero except a maxed-out sentiment score.
    inputs = ScoreInputs(
        technical_score=0.0, trend_score=0.0, volume_score=0.0,
        news_score=0.0, sentiment_score=1.0, portfolio_fit_score=0.0,
    )
    decision = decider.decide(inputs)
    # sentiment weight is 0.05 -> final score 0.05, far below the 0.72 threshold
    assert decision.final_score == 0.05
    assert decision.outcome is DecisionOutcome.NO_TRADE


def _candles(closes: list[float], step_min: int, last_volume: float | None = None):
    out = []
    for i, c in enumerate(closes):
        vol = 1000.0 if last_volume is None or i < len(closes) - 1 else last_volume
        out.append(Candle(BASE + timedelta(minutes=step_min * i), c, c + 1, c - 1, c, vol))
    return out


def test_pipeline_sentiment_only_nudges_executed_trade() -> None:
    config = load_config()
    orch = Orchestrator(
        config, mode=OperatingMode.SHADOW, simulator=PaperCFDSimulator(10_000.0),
        starting_equity=10_000.0, sentiment_agent=SocialSentimentAgent(),
    )
    snap = MarketSnapshot(
        symbol="US500",
        candles_1h=_candles([100.0 + i for i in range(60)], 60),
        candles_15m=_candles([100.0 + i * 0.5 for i in range(40)], 15, last_volume=2000.0),
        price=Price("US500", 119.4, 119.6, NOW),
        social_samples=samples(1.0),
        now=NOW,
    )
    result = orch.run_symbol(snap)
    # The strong technical setup carries the trade; sentiment only nudged it.
    assert result.state is PipelineState.EXECUTED
    assert 0.5 < result.audit["scores"]["sentiment"] <= 1.0
