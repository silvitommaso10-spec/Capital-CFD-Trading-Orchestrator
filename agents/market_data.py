"""Market Data Agent.

Responsible for prices, candles, spread, volume, timestamps and data quality.
It can:

- aggregate a stream of ticks/quotes into OHLCV candles (live WebSocket path);
- fetch OHLCV candles from the Capital.com read-only client (historical path);
- assess data quality (staleness and spread) into flags the Risk Engine and
  the pipeline consume.

Analysis-only: it never places orders.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.config import AppConfig
from capital.models import Price
from .base import BaseAgent, Signal
from .candles import Candle

# Logical timeframe -> Capital.com resolution string.
RESOLUTION = {
    "1H": "HOUR",
    "15m": "MINUTE_15",
    "1m": "MINUTE",
    "5m": "MINUTE_5",
    "4H": "HOUR_4",
    "1D": "DAY",
}

# Logical timeframe -> seconds (for tick aggregation).
TIMEFRAME_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1H": 3600,
    "4H": 14400,
    "1D": 86400,
}


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


@dataclass(frozen=True)
class MarketQuality:
    """Data-quality assessment for a single instrument snapshot."""

    symbol: str
    age_seconds: float
    max_age_seconds: float
    is_stale: bool
    spread: float
    max_spread: float
    is_spread_high: bool
    score: float  # 0.0 (unusable) .. 1.0 (pristine)

    @property
    def ok(self) -> bool:
        return not self.is_stale and not self.is_spread_high


class CandleAggregator:
    """Aggregate ticks/quotes into fixed-interval OHLCV candles."""

    def __init__(self, timeframe_seconds: int) -> None:
        if timeframe_seconds <= 0:
            raise ValueError("timeframe_seconds must be positive")
        self._tf = timeframe_seconds
        self._start: float | None = None
        self._o = self._h = self._l = self._c = 0.0
        self._vol = 0.0
        self.closed: list[Candle] = []

    def _bucket_start(self, ts: datetime) -> float:
        epoch = ts.timestamp()
        return (epoch // self._tf) * self._tf

    def _emit(self) -> Candle:
        assert self._start is not None
        return Candle(
            timestamp=datetime.fromtimestamp(self._start, tz=timezone.utc),
            open=self._o,
            high=self._h,
            low=self._l,
            close=self._c,
            volume=self._vol,
        )

    def add(self, ts: datetime, price: float, volume: float = 0.0) -> Candle | None:
        """Add a tick. Returns the just-closed candle when a bucket rolls over."""

        bucket = self._bucket_start(ts)
        if self._start is None:
            self._start = bucket
            self._o = self._h = self._l = self._c = price
            self._vol = volume
            return None
        if bucket != self._start:
            finished = self._emit()
            self.closed.append(finished)
            self._start = bucket
            self._o = self._h = self._l = self._c = price
            self._vol = volume
            return finished
        # same bucket: update OHLCV
        self._h = max(self._h, price)
        self._l = min(self._l, price)
        self._c = price
        self._vol += volume
        return None

    def flush(self) -> Candle | None:
        """Emit and reset the in-progress candle (e.g. at end of stream)."""

        if self._start is None:
            return None
        finished = self._emit()
        self.closed.append(finished)
        self._start = None
        return finished


class MarketDataAgent(BaseAgent):
    """Provides candles and data-quality assessment."""

    name = "market_data"

    def __init__(self, config: AppConfig, client: Any | None = None) -> None:
        self._config = config
        self._client = client  # CapitalClient (read-only); optional for tests

    # -- candles -----------------------------------------------------------

    def candles(
        self, symbol: str, timeframe: str, max_points: int = 200
    ) -> list[Candle]:
        """Fetch OHLCV candles for ``symbol`` at ``timeframe`` from the broker."""

        if self._client is None:
            raise RuntimeError("MarketDataAgent has no Capital client configured")
        resolution = RESOLUTION.get(timeframe)
        if resolution is None:
            raise ValueError(f"unknown timeframe {timeframe!r}")
        epic = self._config.instruments.by_symbol(symbol).epic
        return self._client.get_candles(epic, resolution, max_points)

    # -- data quality ------------------------------------------------------

    def quality(
        self, symbol: str, price: Price, now: datetime | None = None
    ) -> MarketQuality:
        now = now or datetime.now(timezone.utc)
        inst = self._config.instruments.by_symbol(symbol)
        max_age = self._config.risk.max_data_age_seconds
        max_spread = inst.max_spread

        age = price.age_seconds(now)
        spread = price.spread
        is_stale = age > max_age
        is_spread_high = max_spread > 0 and spread > max_spread

        freshness = _clamp(1.0 - age / max_age) if max_age > 0 else 1.0
        spread_score = _clamp(1.0 - spread / max_spread) if max_spread > 0 else 1.0
        score = 0.0 if (is_stale or is_spread_high) else min(freshness, spread_score)

        return MarketQuality(
            symbol=symbol,
            age_seconds=age,
            max_age_seconds=max_age,
            is_stale=is_stale,
            spread=spread,
            max_spread=max_spread,
            is_spread_high=is_spread_high,
            score=score,
        )

    # -- BaseAgent ---------------------------------------------------------

    def analyze(self, context: dict[str, Any]) -> Signal:
        """Return a Signal carrying the data-quality score.

        ``context`` must contain ``symbol`` and ``price`` (a :class:`Price`).
        """

        q = self.quality(context["symbol"], context["price"], context.get("now"))
        rationale = "ok" if q.ok else (
            "stale" if q.is_stale else "spread_high"
        )
        return Signal(
            self.name,
            q.score,
            rationale,
            metadata={
                "is_stale": q.is_stale,
                "is_spread_high": q.is_spread_high,
                "age_seconds": q.age_seconds,
                "spread": q.spread,
            },
        )
