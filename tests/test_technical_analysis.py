"""Tests for the Technical Analysis Agent."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agents.candles import Candle
from agents.technical_analysis import TechnicalAnalysisAgent, Trend
from risk.models import Direction

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_candles(
    closes: list[float], *, step_min: int, volume: float = 1000.0,
    last_volume: float | None = None, band: float = 1.0,
) -> list[Candle]:
    candles: list[Candle] = []
    for i, close in enumerate(closes):
        vol = volume
        if last_volume is not None and i == len(closes) - 1:
            vol = last_volume
        candles.append(
            Candle(
                timestamp=BASE + timedelta(minutes=step_min * i),
                open=close,
                high=close + band,
                low=close - band,
                close=close,
                volume=vol,
            )
        )
    return candles


def test_uptrend_proposes_long_with_valid_stop_and_target() -> None:
    agent = TechnicalAnalysisAgent()
    c1h = make_candles([100.0 + i for i in range(60)], step_min=60)
    c15 = make_candles(
        [100.0 + i * 0.5 for i in range(40)], step_min=15,
        last_volume=2000.0,
    )
    sig = agent.analyze_full(symbol="US500", candles_1h=c1h, candles_15m=c15)

    assert sig.trend is Trend.UP
    assert sig.direction is Direction.LONG
    assert sig.entry_price is not None
    assert sig.stop_loss is not None and sig.take_profit is not None
    # long: stop below entry, target above entry
    assert sig.stop_loss < sig.entry_price < sig.take_profit
    # reward/risk ~ configured 2.0
    risk = sig.entry_price - sig.stop_loss
    reward = sig.take_profit - sig.entry_price
    assert reward / risk == 2.0
    assert 0.0 <= sig.technical_score <= 1.0
    assert sig.trend_score > 0.0
    assert sig.volume_score > 0.5  # last bar volume spike


def test_downtrend_proposes_short() -> None:
    agent = TechnicalAnalysisAgent()
    c1h = make_candles([200.0 - i for i in range(60)], step_min=60)
    c15 = make_candles([200.0 - i * 0.5 for i in range(40)], step_min=15)
    sig = agent.analyze_full(symbol="US500", candles_1h=c1h, candles_15m=c15)

    assert sig.trend is Trend.DOWN
    assert sig.direction is Direction.SHORT
    assert sig.stop_loss is not None and sig.take_profit is not None
    # short: stop above entry, target below entry
    assert sig.take_profit < sig.entry_price < sig.stop_loss


def test_sideways_yields_no_direction() -> None:
    agent = TechnicalAnalysisAgent()
    flat = [100.0 + (1.0 if i % 2 else -1.0) for i in range(60)]
    c1h = make_candles(flat, step_min=60)
    c15 = make_candles(flat[:40], step_min=15)
    sig = agent.analyze_full(symbol="US500", candles_1h=c1h, candles_15m=c15)

    assert sig.trend is Trend.SIDEWAYS
    assert sig.direction is None
    assert sig.technical_score == 0.0


def test_insufficient_history_is_neutral() -> None:
    agent = TechnicalAnalysisAgent()
    c1h = make_candles([100.0 + i for i in range(10)], step_min=60)
    c15 = make_candles([100.0 + i for i in range(10)], step_min=15)
    sig = agent.analyze_full(symbol="US500", candles_1h=c1h, candles_15m=c15)

    assert sig.direction is None
    assert sig.technical_score == 0.0
    assert "insufficient" in sig.rationale


def test_analyze_returns_signal_for_decision_agent() -> None:
    agent = TechnicalAnalysisAgent()
    c1h = make_candles([100.0 + i for i in range(60)], step_min=60)
    c15 = make_candles([100.0 + i * 0.5 for i in range(40)], step_min=15)
    signal = agent.analyze(
        {"symbol": "US500", "candles_1h": c1h, "candles_15m": c15}
    )
    assert signal.name == "technical_analysis"
    assert 0.0 <= signal.score <= 1.0
    assert signal.metadata["direction"] == "LONG"
