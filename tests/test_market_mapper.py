"""Tests for the symbol <-> epic market mapper."""

from __future__ import annotations

import pytest

from app.config import load_config
from app.errors import MarketNotFoundError
from capital.mapper import MarketMapper


@pytest.fixture()
def mapper() -> MarketMapper:
    config = load_config()
    return MarketMapper(config.instruments)


def test_all_required_symbols_present(mapper: MarketMapper) -> None:
    for symbol in ("US500", "NASDAQ", "GOLD", "USOIL", "BTC"):
        assert symbol in mapper.symbols
        assert mapper.to_epic(symbol)  # non-empty epic


def test_bucket_assignments(mapper: MarketMapper) -> None:
    assert mapper.bucket_of("US500") == "equity_indices"
    assert mapper.bucket_of("NASDAQ") == "equity_indices"
    assert mapper.bucket_of("GOLD") == "metals"
    assert mapper.bucket_of("USOIL") == "energy"
    assert mapper.bucket_of("BTC") == "crypto"


def test_round_trip(mapper: MarketMapper) -> None:
    epic = mapper.to_epic("GOLD")
    assert mapper.to_symbol(epic) == "GOLD"


def test_unknown_symbol_raises(mapper: MarketMapper) -> None:
    with pytest.raises(MarketNotFoundError):
        mapper.to_epic("DOGE")


def test_register_overrides_epic(mapper: MarketMapper) -> None:
    mapper.register("US500", "NEW_EPIC")
    assert mapper.to_epic("US500") == "NEW_EPIC"
    assert mapper.to_symbol("NEW_EPIC") == "US500"
