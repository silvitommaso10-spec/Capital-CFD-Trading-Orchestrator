"""Export historical OHLCV candles from Capital.com to CSV (read-only).

Run this on a machine with network access to the Capital.com demo API and the
credentials in the environment (see .env.example). It downloads candles for a
symbol/timeframe (or for every configured symbol with ``--all``) and writes CSV
files that ``python -m app.backtest`` can consume.

Read-only: it never sends orders.

Examples::

    # one symbol / one timeframe
    python -m app.fetch_candles --symbol US500 --timeframe 1H --max 400 --out us500_1h.csv

    # all symbols, both timeframes (1H + 15m), into ./data/local/
    python -m app.fetch_candles --all --out-dir data/local --max 400
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import load_config
from app.env import load_credentials, load_dotenv
from app.errors import MissingCredentialsError, OrchestratorError
from app.logging_utils import configure_logging, get_logger
from data.csv_writer import write_candles

logger = get_logger("app.fetch_candles")

DEFAULT_TIMEFRAMES = ("1H", "15m")


def candle_filename(symbol: str, timeframe: str) -> str:
    """Filename for a symbol/timeframe export, e.g. ``US500_1H.csv``."""

    return f"{symbol}_{timeframe}.csv"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m app.fetch_candles", description=__doc__)
    p.add_argument("--symbol", help="logical symbol, e.g. US500 (single-file mode)")
    p.add_argument("--timeframe", default="1H",
                   help="1m | 5m | 15m | 1H | 4H | 1D (default: 1H)")
    p.add_argument("--out", help="output CSV path (single-file mode)")
    p.add_argument("--all", action="store_true",
                   help="export every configured symbol on 1H and 15m")
    p.add_argument("--out-dir", dest="out_dir", default="data/local",
                   help="output directory for --all (default: data/local)")
    p.add_argument("--max", type=int, default=400, dest="max_points",
                   help="max candles to fetch per file (default: 400)")
    return p


def run(argv: list[str] | None = None) -> int:
    configure_logging()
    load_dotenv()  # pick up credentials from a local .env if present
    args = build_parser().parse_args(argv)
    config = load_config()

    try:
        credentials = load_credentials(
            api_key_var=config.broker.api_key_var,
            identifier_var=config.broker.identifier_var,
            password_var=config.broker.password_var,
        )
    except MissingCredentialsError as exc:
        logger.error("%s", exc)
        logger.error("Set credentials (see .env.example) before fetching.")
        return 2

    # Imported here so the module loads without the broker deps until needed.
    from agents.market_data import MarketDataAgent
    from capital.client import CapitalClient

    client = CapitalClient(config.broker, credentials)
    client.login()
    agent = MarketDataAgent(config, client)

    # Build the list of (symbol, timeframe, output_path) jobs.
    jobs: list[tuple[str, str, Path]] = []
    if args.all:
        out_dir = Path(args.out_dir)
        for inst in config.instruments.instruments:
            for tf in DEFAULT_TIMEFRAMES:
                jobs.append((inst.symbol, tf, out_dir / candle_filename(inst.symbol, tf)))
    else:
        if not args.symbol or not args.out:
            logger.error("provide --symbol and --out, or use --all")
            return 2
        jobs.append((args.symbol, args.timeframe, Path(args.out)))

    failures = 0
    for symbol, timeframe, path in jobs:
        try:
            candles = agent.candles(symbol, timeframe, args.max_points)
        except OrchestratorError as exc:
            logger.error("could not fetch %s %s: %s", symbol, timeframe, exc)
            failures += 1
            continue
        if not candles:
            logger.warning("no candles returned for %s %s", symbol, timeframe)
            failures += 1
            continue
        write_candles(candles, path)
        logger.info("wrote %d candles -> %s", len(candles), path)

    if failures:
        logger.warning("%d of %d export(s) failed", failures, len(jobs))
        return 1
    logger.info("done: %d file(s) written", len(jobs))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(run())
