"""Read-only milestone entry point.

Demonstrates the first milestone end-to-end against the Capital.com demo API:
load config, read credentials from the environment, open a session, read the
account, and resolve/validate the instrument mapping. It sends no orders.

Usage::

    python -m app.main

Requires the credentials described in ``.env.example`` to be present in the
environment.
"""

from __future__ import annotations

import sys

from app.config import load_config
from app.env import load_credentials
from app.errors import MissingCredentialsError, OrchestratorError
from app.logging_utils import configure_logging, get_logger
from app.modes import is_live_trading_enabled
from capital.client import CapitalClient
from capital.mapper import MarketMapper

logger = get_logger("app.main")


def run() -> int:
    configure_logging()
    config = load_config()

    logger.info("Starting in mode=%s (live trading enabled=%s)",
                config.mode.value, is_live_trading_enabled(config.mode))

    try:
        credentials = load_credentials(
            api_key_var=config.broker.api_key_var,
            identifier_var=config.broker.identifier_var,
            password_var=config.broker.password_var,
        )
    except MissingCredentialsError as exc:
        logger.error("%s", exc)
        logger.error("Set the variables described in .env.example and retry.")
        return 2

    client = CapitalClient(config.broker, credentials)
    mapper = MarketMapper(config.instruments)

    client.login()

    accounts = client.get_accounts()
    for account in accounts:
        logger.info(
            "account %s: balance=%.2f %s available=%.2f",
            account.account_id, account.balance, account.currency, account.available,
        )

    for symbol in mapper.symbols:
        epic = mapper.to_epic(symbol)
        try:
            price = client.get_latest_price(epic)
            logger.info(
                "%s (%s): bid=%.4f offer=%.4f spread=%.4f",
                symbol, epic, price.bid, price.offer, price.spread,
            )
        except OrchestratorError as exc:
            logger.warning("could not read price for %s (%s): %s", symbol, epic, exc)

    logger.info("Read-only run complete; no orders were sent.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(run())
