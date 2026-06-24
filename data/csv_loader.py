"""Load OHLCV candles from CSV files.

Expected header (order-independent, case-insensitive):

    timestamp,open,high,low,close,volume

``timestamp`` may be ISO 8601 (``2026-01-01T00:00:00Z``) or a Unix epoch in
seconds or milliseconds. ``volume`` is optional.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from agents.candles import Candle


def _parse_timestamp(value: str) -> datetime:
    value = value.strip()
    # Numeric epoch (seconds or milliseconds).
    try:
        num = float(value)
        if num > 1e12:  # milliseconds
            num /= 1000.0
        return datetime.fromtimestamp(num, tz=timezone.utc)
    except ValueError:
        pass
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def parse_rows(rows: Iterable[dict[str, str]]) -> list[Candle]:
    candles: list[Candle] = []
    for row in rows:
        norm = {k.strip().lower(): v for k, v in row.items() if k}
        candles.append(
            Candle(
                timestamp=_parse_timestamp(norm["timestamp"]),
                open=float(norm["open"]),
                high=float(norm["high"]),
                low=float(norm["low"]),
                close=float(norm["close"]),
                volume=float(norm.get("volume") or 0.0),
            )
        )
    candles.sort(key=lambda c: c.timestamp)
    return candles


def load_candles(path: str | Path) -> list[Candle]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return parse_rows(reader)
