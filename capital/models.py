"""Typed data models for Capital.com read-only responses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class Account:
    """A single trading account balance snapshot."""

    account_id: str
    currency: str
    balance: float
    available: float
    deposit: float
    profit_loss: float

    @staticmethod
    def from_api(raw: dict[str, Any]) -> "Account":
        balance = raw.get("balance", {}) or {}
        return Account(
            account_id=str(raw.get("accountId", "")),
            currency=str(raw.get("currency", "")),
            balance=float(balance.get("balance", 0.0)),
            available=float(balance.get("available", 0.0)),
            deposit=float(balance.get("deposit", 0.0)),
            profit_loss=float(balance.get("profitLoss", 0.0)),
        )


@dataclass(frozen=True)
class MarketSummary:
    """Lightweight market entry returned by market search."""

    epic: str
    instrument_name: str
    instrument_type: str
    market_status: str
    bid: float | None
    offer: float | None

    @staticmethod
    def from_api(raw: dict[str, Any]) -> "MarketSummary":
        return MarketSummary(
            epic=str(raw.get("epic", "")),
            instrument_name=str(raw.get("instrumentName", "")),
            instrument_type=str(raw.get("instrumentType", "")),
            market_status=str(raw.get("marketStatus", "")),
            bid=_opt_float(raw.get("bid")),
            offer=_opt_float(raw.get("offer")),
        )


@dataclass(frozen=True)
class MarketDetails:
    """Detailed market metadata for a single epic."""

    epic: str
    instrument_name: str
    instrument_type: str
    lot_size: float
    min_deal_size: float
    margin_factor: float
    market_status: str

    @staticmethod
    def from_api(raw: dict[str, Any]) -> "MarketDetails":
        instrument = raw.get("instrument", {}) or {}
        dealing = raw.get("dealingRules", {}) or {}
        snapshot = raw.get("snapshot", {}) or {}
        min_size = (dealing.get("minDealSize", {}) or {}).get("value", 0.0)
        return MarketDetails(
            epic=str(instrument.get("epic", "")),
            instrument_name=str(instrument.get("name", "")),
            instrument_type=str(instrument.get("type", "")),
            lot_size=float(instrument.get("lotSize", 1.0) or 1.0),
            min_deal_size=float(min_size or 0.0),
            margin_factor=float(instrument.get("marginFactor", 0.0) or 0.0),
            market_status=str(snapshot.get("marketStatus", "")),
        )


@dataclass(frozen=True)
class Price:
    """A bid/offer snapshot with a timestamp, used for quality checks."""

    epic: str
    bid: float
    offer: float
    timestamp: datetime

    @property
    def mid(self) -> float:
        return (self.bid + self.offer) / 2.0

    @property
    def spread(self) -> float:
        return self.offer - self.bid

    def age_seconds(self, now: datetime | None = None) -> float:
        now = now or datetime.now(timezone.utc)
        return (now - self.timestamp).total_seconds()


def _opt_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
