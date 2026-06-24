"""OHLCV candle model and helpers shared by the analysis agents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence


@dataclass(frozen=True)
class Candle:
    """A single OHLCV bar for a given timeframe."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


def closes(candles: Sequence[Candle]) -> list[float]:
    return [c.close for c in candles]


def highs(candles: Sequence[Candle]) -> list[float]:
    return [c.high for c in candles]


def lows(candles: Sequence[Candle]) -> list[float]:
    return [c.low for c in candles]


def volumes(candles: Sequence[Candle]) -> list[float]:
    return [c.volume for c in candles]
