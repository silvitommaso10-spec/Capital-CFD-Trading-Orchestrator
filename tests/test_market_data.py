"""Tests for the Market Data Agent: aggregation, candle fetch and quality."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from agents.market_data import CandleAggregator, MarketDataAgent
from app.config import BrokerConfig, HttpConfig, load_config
from app.env import Credentials
from app.modes import OperatingMode
from capital.client import CapitalClient
from capital.models import Price
from capital.transport import HttpResponse

BASE = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)


# -- CandleAggregator ------------------------------------------------------


def test_aggregator_builds_candles_per_bucket() -> None:
    agg = CandleAggregator(timeframe_seconds=900)  # 15 minutes
    # bucket 1: 00:00-00:15
    assert agg.add(BASE, 100.0, 1.0) is None
    assert agg.add(BASE + timedelta(minutes=5), 102.0, 2.0) is None
    assert agg.add(BASE + timedelta(minutes=10), 99.0, 1.0) is None
    # crossing into bucket 2 closes bucket 1
    closed = agg.add(BASE + timedelta(minutes=15), 101.0, 5.0)
    assert closed is not None
    assert closed.open == 100.0
    assert closed.high == 102.0
    assert closed.low == 99.0
    assert closed.close == 99.0
    assert closed.volume == 4.0  # 1 + 2 + 1
    assert closed.timestamp == BASE


def test_aggregator_flush_emits_partial() -> None:
    agg = CandleAggregator(timeframe_seconds=900)
    agg.add(BASE, 100.0, 1.0)
    agg.add(BASE + timedelta(minutes=3), 105.0, 1.0)
    last = agg.flush()
    assert last is not None
    assert last.high == 105.0
    assert len(agg.closed) == 1


# -- candle fetch via read-only client ------------------------------------


class FakeTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self._responses = responses

    def request(self, method: str, url: str, *, headers: Mapping[str, str] | None = None,
                params: Mapping[str, Any] | None = None, json: Any | None = None,
                timeout: float = 15.0) -> HttpResponse:
        return self._responses.pop(0)


def _broker_config() -> BrokerConfig:
    return BrokerConfig(
        name="capital_com", product="CFD", mode=OperatingMode.CAPITAL_DEMO,
        live_trading_enabled=False, rest_base_url="https://x.example.com",
        ws_base_url="wss://x", api_key_var="K", identifier_var="I",
        password_var="P", http=HttpConfig(timeout_seconds=5, max_retries=0, backoff_seconds=0),
    )


def test_client_get_candles_parses_ohlc() -> None:
    transport = FakeTransport([
        HttpResponse(200, {"CST": "c", "X-SECURITY-TOKEN": "t"}),
        HttpResponse(200, {}, {
            "prices": [
                {
                    "snapshotTime": "2026-01-01T00:00:00",
                    "openPrice": {"bid": 100.0, "ask": 100.2},
                    "highPrice": {"bid": 101.0, "ask": 101.2},
                    "lowPrice": {"bid": 99.0, "ask": 99.2},
                    "closePrice": {"bid": 100.5, "ask": 100.7},
                    "lastTradedVolume": 1234,
                }
            ]
        }),
    ])
    client = CapitalClient(_broker_config(), Credentials("k", "i", "p"), transport=transport)
    candles = client.get_candles("US500", "MINUTE_15", 10)
    assert len(candles) == 1
    c = candles[0]
    assert c.open == 100.1   # mid of 100.0/100.2
    assert c.high == 101.1
    assert c.low == 99.1
    assert c.close == 100.6
    assert c.volume == 1234.0


# -- data quality ----------------------------------------------------------


def test_quality_ok_for_fresh_tight_spread() -> None:
    agent = MarketDataAgent(load_config())
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    price = Price("US500", bid=5000.0, offer=5000.3, timestamp=now)  # spread 0.3 < 1.5
    q = agent.quality("US500", price, now=now)
    assert q.ok
    assert not q.is_stale and not q.is_spread_high
    assert q.score > 0.0


def test_quality_flags_stale_data() -> None:
    agent = MarketDataAgent(load_config())
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    old = now - timedelta(seconds=120)  # > max_data_age (30s)
    price = Price("US500", 5000.0, 5000.3, old)
    q = agent.quality("US500", price, now=now)
    assert q.is_stale
    assert not q.ok
    assert q.score == 0.0


def test_quality_flags_high_spread() -> None:
    agent = MarketDataAgent(load_config())
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    price = Price("US500", 5000.0, 5005.0, now)  # spread 5 > max 1.5
    q = agent.quality("US500", price, now=now)
    assert q.is_spread_high
    assert not q.ok
    assert q.score == 0.0


def test_analyze_returns_quality_signal() -> None:
    agent = MarketDataAgent(load_config())
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    price = Price("US500", 5000.0, 5000.2, now)
    signal = agent.analyze({"symbol": "US500", "price": price, "now": now})
    assert signal.name == "market_data"
    assert signal.metadata["is_stale"] is False
    assert 0.0 <= signal.score <= 1.0
