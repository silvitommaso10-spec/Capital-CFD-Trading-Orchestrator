"""Tests for the technical indicators."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agents import indicators as ind
from agents.candles import Candle


def test_sma_exact() -> None:
    assert ind.sma([1, 2, 3, 4], 2) == [None, 1.5, 2.5, 3.5]


def test_sma_too_short() -> None:
    assert ind.sma([1, 2], 5) == [None, None]


def test_ema_seeded_with_sma() -> None:
    # period 3: seed = SMA(1,2,3)=2 at idx2; k=0.5 -> 3, then 4
    assert ind.ema([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]


def test_rsi_bounds_and_extremes() -> None:
    rising = list(range(1, 30))
    falling = list(range(30, 1, -1))
    assert ind.latest(ind.rsi(rising, 14)) == 100.0
    assert ind.latest(ind.rsi(falling, 14)) == 0.0
    mixed = [10, 11, 10, 12, 11, 13, 12, 14, 13, 15, 14, 16, 15, 17, 16, 18]
    r = ind.latest(ind.rsi(mixed, 14))
    assert r is not None and 0.0 < r < 100.0


def test_atr_wilder_small_case() -> None:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = [
        Candle(base, 9, 10, 8, 9),
        Candle(base + timedelta(minutes=15), 9, 12, 9, 11),
        Candle(base + timedelta(minutes=30), 11, 11, 10, 10),
    ]
    # TR = [2, 3, 1]; seed ATR(2) at idx1 = 2.5; idx2 = (2.5*1 + 1)/2 = 1.75
    a = ind.atr(candles, 2)
    assert a[1] == pytest.approx(2.5)
    assert a[2] == pytest.approx(1.75)


def test_macd_histogram_sign_follows_momentum() -> None:
    # Flat then a sharp move: the MACD line accelerates while the signal lags,
    # so the histogram sign reflects the new momentum.
    rising = [100.0] * 40 + [100.0 + 2.0 * i for i in range(1, 21)]
    falling = [100.0] * 40 + [100.0 - 2.0 * i for i in range(1, 21)]
    assert ind.latest(ind.macd(rising)[2]) > 0  # histogram positive in uptrend
    assert ind.latest(ind.macd(falling)[2]) < 0  # negative in downtrend


def test_latest_returns_last_defined() -> None:
    assert ind.latest([None, 1.0, None]) == 1.0
    assert ind.latest([None, None]) is None
