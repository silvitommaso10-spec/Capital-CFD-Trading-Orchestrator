"""Technical indicators.

Pure functions over price/candle sequences. Each indicator returns a list the
same length as its input, with ``None`` for the warm-up period where the value
is not yet defined. Smoothed indicators (RSI, ATR) use Wilder's smoothing.
"""

from __future__ import annotations

from typing import Sequence

from .candles import Candle

Number = float
OptFloat = float | None


def sma(values: Sequence[float], period: int) -> list[OptFloat]:
    """Simple moving average."""

    if period <= 0:
        raise ValueError("period must be positive")
    out: list[OptFloat] = [None] * len(values)
    if len(values) < period:
        return out
    window = sum(values[:period])
    out[period - 1] = window / period
    for i in range(period, len(values)):
        window += values[i] - values[i - period]
        out[i] = window / period
    return out


def ema(values: Sequence[float], period: int) -> list[OptFloat]:
    """Exponential moving average, seeded with the SMA of the first window."""

    if period <= 0:
        raise ValueError("period must be positive")
    out: list[OptFloat] = [None] * len(values)
    if len(values) < period:
        return out
    k = 2.0 / (period + 1)
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(values: Sequence[float], period: int = 14) -> list[OptFloat]:
    """Relative Strength Index using Wilder's smoothing."""

    if period <= 0:
        raise ValueError("period must be positive")
    out: list[OptFloat] = [None] * len(values)
    if len(values) <= period:
        return out

    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        delta = values[i] - values[i - 1]
        gains += max(delta, 0.0)
        losses += max(-delta, 0.0)
    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = _rsi_from(avg_gain, avg_loss)

    for i in range(period + 1, len(values)):
        delta = values[i] - values[i - 1]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        out[i] = _rsi_from(avg_gain, avg_loss)
    return out


def _rsi_from(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0.0:
        return 100.0 if avg_gain > 0.0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def macd(
    values: Sequence[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[list[OptFloat], list[OptFloat], list[OptFloat]]:
    """MACD line, signal line and histogram."""

    ema_fast = ema(values, fast)
    ema_slow = ema(values, slow)
    macd_line: list[OptFloat] = [
        (f - s) if (f is not None and s is not None) else None
        for f, s in zip(ema_fast, ema_slow)
    ]

    # Signal line is an EMA over the dense (non-None) MACD values.
    first = next((i for i, v in enumerate(macd_line) if v is not None), None)
    signal_line: list[OptFloat] = [None] * len(values)
    if first is not None:
        dense = [v for v in macd_line[first:] if v is not None]
        sig_dense = ema(dense, signal)
        for offset, v in enumerate(sig_dense):
            signal_line[first + offset] = v

    hist: list[OptFloat] = [
        (m - s) if (m is not None and s is not None) else None
        for m, s in zip(macd_line, signal_line)
    ]
    return macd_line, signal_line, hist


def true_range(candles: Sequence[Candle]) -> list[float]:
    """True range for each bar (first bar uses high-low)."""

    out: list[float] = []
    prev_close: float | None = None
    for c in candles:
        if prev_close is None:
            out.append(c.high - c.low)
        else:
            out.append(
                max(
                    c.high - c.low,
                    abs(c.high - prev_close),
                    abs(c.low - prev_close),
                )
            )
        prev_close = c.close
    return out


def atr(candles: Sequence[Candle], period: int = 14) -> list[OptFloat]:
    """Average True Range using Wilder's smoothing."""

    if period <= 0:
        raise ValueError("period must be positive")
    tr = true_range(candles)
    out: list[OptFloat] = [None] * len(candles)
    if len(candles) < period:
        return out
    prev = sum(tr[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(candles)):
        prev = (prev * (period - 1) + tr[i]) / period
        out[i] = prev
    return out


def latest(values: Sequence[OptFloat]) -> OptFloat:
    """Return the last non-None value, or None if there is none."""

    for v in reversed(values):
        if v is not None:
            return v
    return None
