"""Tests for the multi-symbol backtest CLI (app.backtest_all)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from agents.candles import Candle
from app.fetch_candles import candle_filename
from app import backtest_all
from data.csv_writer import write_candles

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _series(n: int, start: float, step: float, step_min: int) -> list[Candle]:
    out = []
    for i in range(n):
        close = start + step * i
        out.append(
            Candle(
                timestamp=BASE + timedelta(minutes=step_min * i),
                open=close, high=close + 1.0, low=close - 1.0, close=close,
                volume=1000.0,
            )
        )
    return out


def _write_symbol(data_dir: Path, symbol: str) -> None:
    write_candles(_series(80, 100.0, 1.0, 60),
                  str(data_dir / candle_filename(symbol, "1H")))
    write_candles(_series(320, 100.0, 0.25, 15),
                  str(data_dir / candle_filename(symbol, "15m")))


def test_run_summarises_available_symbols(tmp_path, capsys) -> None:
    _write_symbol(tmp_path, "GOLD")  # one configured symbol with data

    rc = backtest_all.run([
        "--data-dir", str(tmp_path),
        "--trade-threshold", "0.5",
        "--watchlist-threshold", "0.4",
    ])
    out = capsys.readouterr().out

    assert rc == 0
    assert "GOLD" in out
    assert "Backtest summary" in out
    assert "TOTAL" in out
    # symbols without CSVs are reported as skipped
    assert "Skipped" in out
    assert "US500" in out  # configured but no data -> skipped list


def test_run_errors_when_no_data(tmp_path, capsys) -> None:
    rc = backtest_all.run(["--data-dir", str(tmp_path)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "no candle CSVs" in err
