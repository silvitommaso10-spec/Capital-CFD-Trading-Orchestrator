"""Tests for the News Macro Agent and its pipeline integration."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agents.candles import Candle
from agents.news_macro import Impact, MacroEvent, NewsMacroAgent
from app.config import load_config, load_news_config
from app.modes import OperatingMode
from app.orchestrator import MarketSnapshot, Orchestrator, PipelineState
from backtesting.paper_simulator import PaperCFDSimulator
from capital.models import Price
from risk.models import Direction

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def agent() -> NewsMacroAgent:
    return NewsMacroAgent(load_news_config())


# -- agent unit tests ------------------------------------------------------


def test_affects_bucket_mapping() -> None:
    a = agent()
    assert a.affects_bucket("central_bank", "equity_indices")
    assert a.affects_bucket("energy_inventories", "energy")
    assert not a.affects_bucket("energy_inventories", "equity_indices")


def test_no_events_is_neutral() -> None:
    a = agent()
    result = a.assess("equity_indices", NOW, [])
    assert result.news_score == 0.5
    assert not result.block


def test_high_impact_event_triggers_blackout() -> None:
    a = agent()
    events = [MacroEvent(NOW, "central_bank", Impact.HIGH, sentiment=0.3)]
    result = a.assess("equity_indices", NOW, events)
    assert result.in_blackout
    assert result.block
    assert result.news_score == 0.2


def test_contradictory_unconfirmed_news_is_conflict() -> None:
    a = agent()
    events = [
        MacroEvent(NOW - timedelta(minutes=30), "inflation", Impact.MEDIUM,
                   sentiment=0.6, confirmed=False),
        MacroEvent(NOW - timedelta(minutes=20), "central_bank", Impact.MEDIUM,
                   sentiment=-0.6, confirmed=False),
    ]
    result = a.assess("equity_indices", NOW, events)
    assert result.has_conflict
    assert result.block
    assert result.news_score == 0.2


def test_confirmed_bullish_news_oriented_by_direction() -> None:
    a = agent()
    events = [MacroEvent(NOW - timedelta(minutes=30), "inflation", Impact.MEDIUM,
                         sentiment=0.8, confirmed=True)]
    long_score = a.assess("equity_indices", NOW, events, Direction.LONG).news_score
    short_score = a.assess("equity_indices", NOW, events, Direction.SHORT).news_score
    assert long_score > 0.5      # bullish news supports a long
    assert short_score < 0.5     # the same news opposes a short
    assert abs((long_score - 0.5) - (0.5 - short_score)) < 1e-9


def test_irrelevant_events_ignored() -> None:
    a = agent()
    # energy_inventories does not affect equity_indices
    events = [MacroEvent(NOW, "energy_inventories", Impact.HIGH, sentiment=-1.0)]
    result = a.assess("equity_indices", NOW, events)
    assert result.news_score == 0.5
    assert not result.block


def test_analyze_returns_signal() -> None:
    a = agent()
    signal = a.analyze({"bucket": "equity_indices", "now": NOW, "events": []})
    assert signal.name == "news_macro"
    assert signal.metadata["block"] is False


# -- pipeline integration --------------------------------------------------


def _candles(closes: list[float], step_min: int, last_volume: float | None = None):
    out = []
    for i, c in enumerate(closes):
        vol = 1000.0 if last_volume is None or i < len(closes) - 1 else last_volume
        out.append(Candle(BASE + timedelta(minutes=step_min * i), c, c + 1, c - 1, c, vol))
    return out


def _uptrend(events: list[MacroEvent]) -> MarketSnapshot:
    return MarketSnapshot(
        symbol="US500",
        candles_1h=_candles([100.0 + i for i in range(60)], 60),
        candles_15m=_candles([100.0 + i * 0.5 for i in range(40)], 15, last_volume=2000.0),
        price=Price("US500", 119.4, 119.6, NOW),
        macro_events=events,
        now=NOW,
    )


def _orchestrator() -> Orchestrator:
    config = load_config()
    return Orchestrator(
        config,
        mode=OperatingMode.SHADOW,
        simulator=PaperCFDSimulator(10_000.0),
        starting_equity=10_000.0,
        news_agent=NewsMacroAgent(load_news_config()),
    )


def test_pipeline_waits_during_blackout() -> None:
    orch = _orchestrator()
    events = [MacroEvent(NOW, "central_bank", Impact.HIGH, sentiment=0.0)]
    result = orch.run_symbol(_uptrend(events))
    assert result.state is PipelineState.WAIT
    assert result.risk is None


def test_pipeline_executes_with_supportive_news() -> None:
    orch = _orchestrator()
    events = [MacroEvent(NOW - timedelta(minutes=30), "inflation", Impact.MEDIUM,
                         sentiment=0.8, confirmed=True)]
    result = orch.run_symbol(_uptrend(events))
    assert result.state is PipelineState.EXECUTED
    assert result.audit["scores"]["news"] > 0.5
