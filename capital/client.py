"""Read-only Capital.com demo API client.

This client intentionally exposes *only* read operations. There is no method
to open, amend, or close positions or working orders. Any attempt to reach a
trading endpoint raises :class:`LiveTradingDisabledError`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.config import BrokerConfig
from app.env import Credentials
from app.errors import (
    BrokerError,
    LiveTradingDisabledError,
    MarketNotFoundError,
    SessionExpiredError,
)
from agents.candles import Candle
from app.logging_utils import get_logger
from .auth import CapitalSession, create_session
from .models import Account, MarketDetails, MarketSummary, Price
from .transport import HttpResponse, RequestsTransport, Transport

logger = get_logger(__name__)


class CapitalClient:
    """Read-only access to the Capital.com demo API."""

    def __init__(
        self,
        config: BrokerConfig,
        credentials: Credentials,
        transport: Transport | None = None,
    ) -> None:
        self._config = config
        self._credentials = credentials
        self._transport: Transport = transport or RequestsTransport(
            max_retries=config.http.max_retries,
            backoff_seconds=config.http.backoff_seconds,
        )
        self._session: CapitalSession | None = None

    # -- session management ------------------------------------------------

    def login(self) -> CapitalSession:
        self._session = create_session(
            transport=self._transport,
            base_url=self._config.rest_base_url,
            credentials=self._credentials,
            timeout=self._config.http.timeout_seconds,
        )
        return self._session

    def _ensure_session(self) -> CapitalSession:
        if self._session is None or self._session.is_expired(
            self._config.session_refresh_margin_seconds
        ):
            return self.login()
        return self._session

    # -- low-level GET -----------------------------------------------------

    def _get(self, path: str, params: dict[str, Any] | None = None) -> HttpResponse:
        session = self._ensure_session()
        url = f"{self._config.rest_base_url.rstrip('/')}{path}"
        headers = {"Accept": "application/json", **session.auth_headers()}
        resp = self._transport.request(
            "GET",
            url,
            headers=headers,
            params=params,
            timeout=self._config.http.timeout_seconds,
        )
        if resp.status_code in (401, 403):
            raise SessionExpiredError(
                f"Session rejected with HTTP {resp.status_code} for {path}"
            )
        if resp.status_code == 404:
            raise MarketNotFoundError(f"Not found: {path}")
        if not resp.ok:
            raise BrokerError(f"GET {path} failed with HTTP {resp.status_code}")
        return resp

    # -- read-only endpoints ----------------------------------------------

    def get_accounts(self) -> list[Account]:
        resp = self._get("/api/v1/accounts")
        body = resp.json_body or {}
        return [Account.from_api(a) for a in body.get("accounts", [])]

    def search_markets(self, search_term: str) -> list[MarketSummary]:
        resp = self._get("/api/v1/markets", params={"searchTerm": search_term})
        body = resp.json_body or {}
        return [MarketSummary.from_api(m) for m in body.get("markets", [])]

    def get_market_details(self, epic: str) -> MarketDetails:
        resp = self._get(f"/api/v1/markets/{epic}")
        return MarketDetails.from_api(resp.json_body or {})

    def get_latest_price(self, epic: str) -> Price:
        """Return the latest bid/offer snapshot for ``epic``."""

        resp = self._get(f"/api/v1/markets/{epic}")
        body = resp.json_body or {}
        snapshot = body.get("snapshot", {}) or {}
        bid = snapshot.get("bid")
        offer = snapshot.get("offer")
        if bid is None or offer is None:
            raise BrokerError(f"No price snapshot available for {epic}")
        return Price(
            epic=epic,
            bid=float(bid),
            offer=float(offer),
            timestamp=_parse_timestamp(snapshot.get("updateTime")),
        )

    def get_historical_prices(
        self, epic: str, resolution: str = "MINUTE_15", max_points: int = 100
    ) -> list[Price]:
        """Return historical price points for ``epic``.

        ``resolution`` follows the Capital.com convention (e.g. ``MINUTE_15``,
        ``HOUR``). Read-only.
        """

        resp = self._get(
            f"/api/v1/prices/{epic}",
            params={"resolution": resolution, "max": max_points},
        )
        body = resp.json_body or {}
        prices: list[Price] = []
        for point in body.get("prices", []):
            close = point.get("closePrice", {}) or {}
            bid = close.get("bid")
            offer = close.get("ask", close.get("offer"))
            if bid is None or offer is None:
                continue
            prices.append(
                Price(
                    epic=epic,
                    bid=float(bid),
                    offer=float(offer),
                    timestamp=_parse_timestamp(point.get("snapshotTime")),
                )
            )
        return prices

    def get_candles(
        self, epic: str, resolution: str = "MINUTE_15", max_points: int = 200
    ) -> list[Candle]:
        """Return OHLCV candles for ``epic`` (mid prices). Read-only.

        ``resolution`` follows the Capital.com convention (e.g. ``MINUTE_15``,
        ``HOUR``).
        """

        resp = self._get(
            f"/api/v1/prices/{epic}",
            params={"resolution": resolution, "max": max_points},
        )
        body = resp.json_body or {}
        candles: list[Candle] = []
        for point in body.get("prices", []):
            o = _mid(point.get("openPrice"))
            h = _mid(point.get("highPrice"))
            low = _mid(point.get("lowPrice"))
            c = _mid(point.get("closePrice"))
            if None in (o, h, low, c):
                continue
            candles.append(
                Candle(
                    timestamp=_parse_timestamp(point.get("snapshotTime")),
                    open=o,  # type: ignore[arg-type]
                    high=h,  # type: ignore[arg-type]
                    low=low,  # type: ignore[arg-type]
                    close=c,  # type: ignore[arg-type]
                    volume=float(point.get("lastTradedVolume", 0.0) or 0.0),
                )
            )
        return candles

    # -- trading is disabled ----------------------------------------------

    def place_order(self, *args: Any, **kwargs: Any) -> None:
        """Disabled. This client cannot send orders."""

        raise LiveTradingDisabledError(
            "CapitalClient is read-only; order placement is not implemented "
            "and live trading is disabled in this version."
        )

    # Common alias names guarded for safety.
    create_position = place_order
    close_position = place_order
    update_position = place_order


def _mid(price_obj: Any) -> float | None:
    """Mid of a Capital.com ``{bid, ask}`` price object."""

    if not isinstance(price_obj, dict):
        return None
    bid = price_obj.get("bid")
    ask = price_obj.get("ask", price_obj.get("offer"))
    if bid is None or ask is None:
        return None
    return (float(bid) + float(ask)) / 2.0


def _parse_timestamp(value: Any) -> datetime:
    """Parse Capital.com timestamps (epoch ms or ISO 8601) to aware datetime."""

    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc)
    text = str(value)
    try:
        # Capital.com ISO timestamps may lack timezone info -> assume UTC.
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return datetime.now(timezone.utc)
