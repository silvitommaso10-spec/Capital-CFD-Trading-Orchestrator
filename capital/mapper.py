"""Mapping between logical symbols and Capital.com epics."""

from __future__ import annotations

from app.config import InstrumentsConfig
from app.errors import MarketNotFoundError


class MarketMapper:
    """Resolve logical symbols (US500, NASDAQ, ...) to Capital.com epics.

    The mapping is seeded from ``config/instruments.yaml``. During the
    read-only milestone the resolved epics are validated against the broker's
    market search, and discovered epics can be registered to override the
    defaults.
    """

    def __init__(self, instruments: InstrumentsConfig) -> None:
        self._symbol_to_epic: dict[str, str] = {
            inst.symbol: inst.epic for inst in instruments.instruments
        }
        self._epic_to_symbol: dict[str, str] = {
            inst.epic: inst.symbol for inst in instruments.instruments
        }
        self._symbol_to_bucket: dict[str, str] = {
            inst.symbol: inst.bucket for inst in instruments.instruments
        }

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(self._symbol_to_epic.keys())

    def to_epic(self, symbol: str) -> str:
        try:
            return self._symbol_to_epic[symbol]
        except KeyError:
            raise MarketNotFoundError(
                f"No epic mapping for symbol {symbol!r}"
            ) from None

    def to_symbol(self, epic: str) -> str:
        try:
            return self._epic_to_symbol[epic]
        except KeyError:
            raise MarketNotFoundError(
                f"No symbol mapping for epic {epic!r}"
            ) from None

    def bucket_of(self, symbol: str) -> str:
        try:
            return self._symbol_to_bucket[symbol]
        except KeyError:
            raise MarketNotFoundError(
                f"No bucket for symbol {symbol!r}"
            ) from None

    def register(self, symbol: str, epic: str) -> None:
        """Override/confirm the epic for a symbol (e.g. after market search)."""

        self._symbol_to_epic[symbol] = epic
        self._epic_to_symbol[epic] = symbol
