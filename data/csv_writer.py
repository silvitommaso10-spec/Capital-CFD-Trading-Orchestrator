"""Write OHLCV candles to a CSV file (round-trips with ``data.csv_loader``)."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from agents.candles import Candle

HEADER = ["timestamp", "open", "high", "low", "close", "volume"]


def write_candles(candles: Iterable[Candle], path: str | Path) -> Path:
    """Write candles as ``timestamp,open,high,low,close,volume`` (ISO timestamps)."""

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        for c in candles:
            writer.writerow(
                [c.timestamp.isoformat(), c.open, c.high, c.low, c.close, c.volume]
            )
    return out
