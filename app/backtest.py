"""Backtest CLI.

Run a single-symbol backtest of the decision pipeline and print a report.

Examples::

    # synthetic demo (no data files needed)
    python -m app.backtest --demo

    # from CSV candle files
    python -m app.backtest --symbol US500 \
        --candles-1h data/local/US500_1h.csv \
        --candles-15m data/local/US500_15m.csv

CSV header: ``timestamp,open,high,low,close,volume`` (see data/csv_loader.py).
This is read-only and runs in BACKTEST mode; no orders are sent to any broker.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

from agents.candles import Candle
from agents.decision_agent import DecisionAgent
from app.config import load_config
from app.logging_utils import configure_logging
from app.reporting import format_backtest_report
from backtesting.engine import BacktestEngine
from data.csv_loader import load_candles


def _demo_series(n: int, start: float, step: float, step_min: int) -> list[Candle]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    out = []
    for i in range(n):
        close = start + step * i
        out.append(
            Candle(
                timestamp=base + timedelta(minutes=step_min * i),
                open=close, high=close + 1.0, low=close - 1.0, close=close,
                volume=1000.0,
            )
        )
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m app.backtest", description=__doc__)
    p.add_argument("--symbol", default="US500")
    p.add_argument("--candles-1h", dest="candles_1h")
    p.add_argument("--candles-15m", dest="candles_15m")
    p.add_argument("--balance", type=float, default=10_000.0)
    p.add_argument("--spread", type=float, default=0.2, help="assumed spread")
    p.add_argument("--news-score", type=float, default=0.5)
    p.add_argument("--sentiment-score", type=float, default=0.5)
    p.add_argument("--trade-threshold", type=float, default=0.72)
    p.add_argument("--watchlist-threshold", type=float, default=0.60)
    p.add_argument("--demo", action="store_true", help="run on synthetic uptrend data")
    return p


def run(argv: list[str] | None = None) -> int:
    configure_logging()
    args = build_parser().parse_args(argv)
    config = load_config()

    if args.demo:
        candles_1h = _demo_series(80, 100.0, 1.0, 60)
        candles_15m = _demo_series(320, 100.0, 0.25, 15)
    else:
        if not args.candles_1h or not args.candles_15m:
            print("error: provide --candles-1h and --candles-15m, or use --demo",
                  file=sys.stderr)
            return 2
        candles_1h = load_candles(args.candles_1h)
        candles_15m = load_candles(args.candles_15m)

    engine = BacktestEngine(
        config,
        starting_balance=args.balance,
        assumed_spread=args.spread,
        news_score=args.news_score,
        sentiment_score=args.sentiment_score,
        decision_agent=DecisionAgent(
            trade_threshold=args.trade_threshold,
            watchlist_threshold=args.watchlist_threshold,
        ),
    )
    result = engine.run(args.symbol, candles_1h, candles_15m)
    print(format_backtest_report(result))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(run())
