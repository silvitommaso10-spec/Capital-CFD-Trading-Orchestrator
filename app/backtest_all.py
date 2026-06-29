"""Multi-symbol backtest CLI.

Backtest every configured instrument that has candle CSVs in a data directory
and print a side-by-side summary table.

For each instrument ``SYMBOL`` the loader expects two files in ``--data-dir``::

    {SYMBOL}_1H.csv     # 1-hour candles (trend frame)
    {SYMBOL}_15m.csv    # 15-minute candles (timing frame)

(matching the names produced by ``python -m app.fetch_candles --all``).
Instruments missing either file are skipped and listed at the end.

Example::

    python -m app.backtest_all --data-dir data/local
    python -m app.backtest_all --data-dir data/local --trade-threshold 0.66

This is read-only and runs in BACKTEST mode; no orders are sent to any broker.
"""

from __future__ import annotations

import argparse
import os
import sys

from agents.decision_agent import DecisionAgent
from app.config import load_config
from app.fetch_candles import candle_filename
from app.logging_utils import configure_logging
from backtesting.engine import BacktestEngine, BacktestResult
from data.csv_loader import load_candles


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m app.backtest_all", description=__doc__
    )
    p.add_argument("--data-dir", default="data/local",
                   help="directory holding {SYMBOL}_1H.csv / {SYMBOL}_15m.csv")
    p.add_argument("--balance", type=float, default=10_000.0)
    p.add_argument("--spread", type=float, default=0.2, help="assumed spread")
    p.add_argument("--news-score", type=float, default=0.5)
    p.add_argument("--sentiment-score", type=float, default=0.5)
    p.add_argument("--trade-threshold", type=float, default=0.72)
    p.add_argument("--watchlist-threshold", type=float, default=0.60)
    return p


def _format_table(results: list[BacktestResult]) -> str:
    """Render a fixed-width comparison table of backtest results."""
    header = (
        f"{'SYMBOL':<8} {'TRADES':>6} {'WINS':>5} {'WIN%':>6} "
        f"{'NET PnL':>11} {'RET%':>7} {'PF':>6} {'MAXDD%':>7}"
    )
    lines = [header, "-" * len(header)]
    tot_pnl = 0.0
    tot_trades = 0
    for r in results:
        m = r.metrics
        tot_pnl += m.net_pnl
        tot_trades += m.num_trades
        pf = "inf" if m.profit_factor == float("inf") else f"{m.profit_factor:.2f}"
        lines.append(
            f"{r.symbol:<8} {m.num_trades:>6} {m.wins:>5} "
            f"{m.win_rate * 100:>5.1f}% {m.net_pnl:>+11.2f} "
            f"{m.return_pct * 100:>+6.2f}% {pf:>6} {m.max_drawdown_pct * 100:>6.2f}%"
        )
    lines.append("-" * len(header))
    lines.append(
        f"{'TOTAL':<8} {tot_trades:>6} {'':>5} {'':>6} {tot_pnl:>+11.2f}"
    )
    return "\n".join(lines)


def run(argv: list[str] | None = None) -> int:
    configure_logging()
    args = build_parser().parse_args(argv)
    config = load_config()

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

    results: list[BacktestResult] = []
    skipped: list[str] = []
    for inst in config.instruments.instruments:
        path_1h = os.path.join(args.data_dir, candle_filename(inst.symbol, "1H"))
        path_15m = os.path.join(args.data_dir, candle_filename(inst.symbol, "15m"))
        if not (os.path.exists(path_1h) and os.path.exists(path_15m)):
            skipped.append(inst.symbol)
            continue
        candles_1h = load_candles(path_1h)
        candles_15m = load_candles(path_15m)
        results.append(engine.run(inst.symbol, candles_1h, candles_15m))

    if not results:
        print(f"error: no candle CSVs found in {args.data_dir!r} "
              f"(expected e.g. {candle_filename('GOLD', '1H')})", file=sys.stderr)
        return 2

    print(f"Backtest summary  (data: {args.data_dir}, "
          f"trade>={args.trade_threshold:.2f})")
    print(_format_table(results))
    if skipped:
        print(f"\nSkipped (no data): {', '.join(skipped)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(run())
