"""Tests for CSV candle writing (round-trip with the loader)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agents.candles import Candle
from data.csv_loader import load_candles
from data.csv_writer import write_candles

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_write_then_load_round_trips(tmp_path) -> None:
    candles = [
        Candle(BASE + timedelta(minutes=15 * i), 100 + i, 101 + i, 99 + i,
               100.5 + i, 1000.0 + i)
        for i in range(5)
    ]
    path = write_candles(candles, tmp_path / "out" / "c.csv")
    assert path.exists()

    loaded = load_candles(path)
    assert len(loaded) == 5
    assert loaded[0].open == 100.0
    assert loaded[0].close == 100.5
    assert loaded[4].volume == 1004.0
    # timestamps preserved and ascending
    assert loaded[0].timestamp == BASE
    assert loaded[0].timestamp < loaded[1].timestamp


def test_candle_filename() -> None:
    from app.fetch_candles import candle_filename

    assert candle_filename("US500", "1H") == "US500_1H.csv"
    assert candle_filename("BTC", "15m") == "BTC_15m.csv"

