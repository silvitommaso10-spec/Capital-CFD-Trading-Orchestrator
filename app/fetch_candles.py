"""Export historical OHLCV candles from Capital.com to CSV (read-only).

Run this on a machine with network access to the Capital.com demo API and the
credentials in the environment (see .env.example). It downloads candles for a
symbol/timeframe and writes a CSV that ``python -m app.backtest`` can consume.

Read-only: it never sends orders.

Examples::

    python -m app.fetch_candles --symbol US500 --timeframe 1H  --max 400 --out us500_1h.csv
    python -m app.fetch_candles --symbol US500 --timeframe 15m --max 400 --out us500_15m.csv
"""

from __future__ import annotations

import argparse
import sys

from app.config import load_config
from app.env import load_credentials
from app.errors import MissingCredentialsError, OrchestratorError
from app.logging_utils import configure_logging, get_logger
from data.csv_writer import write_candles

logger = get_logger("app.fetch_candles")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m app.fetch_candles", description=__doc__)
    p.add_argument("--symbol", required=True, help="logical symbol, e.g. US500")
    p.add_argument("--timeframe", default="1H",
                   help="1m | 5m | 15m | 1H | 4H | 1D (default: 1H)")
    p.add_argument("--max", type=int, default=400, dest="max_points",
                   help="max candles to fetch (default: 400)")
    p.add_argument("--out", required=True, help="output CSV path")
    return p


def run(argv: list[str] | None = None) -> int:
    configure_logging()
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

    try:
        candles = agent.candles(args.symbol, args.timeframe, args.max_points)
    except OrchestratorError as exc:
        logger.error("could not fetch candles: %s", exc)
        return 1

    if not candles:
        logger.error("no candles returned for %s %s", args.symbol, args.timeframe)
        return 1

    out = write_candles(candles, args.out)
    logger.info("wrote %d candles to %s", len(candles), out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(run())
