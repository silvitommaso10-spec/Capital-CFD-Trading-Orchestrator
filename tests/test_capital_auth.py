"""Tests for Capital.com authentication and the read-only client guards.

These run entirely against a fake transport; no network access is required.
"""

from __future__ import annotations

from typing import Any, Mapping

import pytest

from app.config import BrokerConfig, HttpConfig
from app.env import Credentials
from app.errors import AuthenticationError, LiveTradingDisabledError
from app.modes import OperatingMode
from capital.auth import create_session
from capital.client import CapitalClient
from capital.transport import HttpResponse


class FakeTransport:
    """Canned transport returning queued responses and recording requests."""

    def __init__(self, responses: list[HttpResponse]) -> None:
        self._responses = responses
        self.calls: list[dict[str, Any]] = []

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        json: Any | None = None,
        timeout: float = 15.0,
    ) -> HttpResponse:
        self.calls.append(
            {"method": method, "url": url, "headers": dict(headers or {}),
             "params": dict(params or {}), "json": json}
        )
        return self._responses.pop(0)


def make_broker_config() -> BrokerConfig:
    return BrokerConfig(
        name="capital_com",
        product="CFD",
        mode=OperatingMode.CAPITAL_DEMO,
        live_trading_enabled=False,
        rest_base_url="https://demo-api-capital.example.com",
        ws_base_url="wss://example.com",
        api_key_var="CAPITAL_API_KEY",
        identifier_var="CAPITAL_IDENTIFIER",
        password_var="CAPITAL_API_PASSWORD",
        http=HttpConfig(timeout_seconds=5, max_retries=0, backoff_seconds=0),
    )


CREDS = Credentials(api_key="k", identifier="id", password="pw")


def test_create_session_success() -> None:
    transport = FakeTransport(
        [HttpResponse(200, {"CST": "cst-123", "X-SECURITY-TOKEN": "tok-456"})]
    )
    session = create_session(
        transport=transport,
        base_url="https://demo-api-capital.example.com",
        credentials=CREDS,
    )
    assert session.cst == "cst-123"
    assert session.security_token == "tok-456"
    assert session.auth_headers() == {"CST": "cst-123", "X-SECURITY-TOKEN": "tok-456"}
    # The API key was sent as a header, never the password in the URL/params.
    assert transport.calls[0]["headers"]["X-CAP-API-KEY"] == "k"


def test_session_repr_hides_secrets() -> None:
    transport = FakeTransport(
        [HttpResponse(200, {"CST": "cst-123", "X-SECURITY-TOKEN": "tok-456"})]
    )
    session = create_session(
        transport=transport,
        base_url="https://demo-api-capital.example.com",
        credentials=CREDS,
    )
    text = repr(session)
    assert "cst-123" not in text and "tok-456" not in text


def test_create_session_failure_raises() -> None:
    transport = FakeTransport([HttpResponse(401, {}, {"errorCode": "invalid"})])
    with pytest.raises(AuthenticationError):
        create_session(
            transport=transport,
            base_url="https://demo-api-capital.example.com",
            credentials=CREDS,
        )


def test_get_accounts_parses_response() -> None:
    transport = FakeTransport(
        [
            HttpResponse(200, {"CST": "c", "X-SECURITY-TOKEN": "t"}),
            HttpResponse(
                200,
                {},
                {
                    "accounts": [
                        {
                            "accountId": "demo-1",
                            "currency": "USD",
                            "balance": {
                                "balance": 10000.0,
                                "available": 9500.0,
                                "deposit": 500.0,
                                "profitLoss": 0.0,
                            },
                        }
                    ]
                },
            ),
        ]
    )
    client = CapitalClient(make_broker_config(), CREDS, transport=transport)
    accounts = client.get_accounts()
    assert len(accounts) == 1
    assert accounts[0].account_id == "demo-1"
    assert accounts[0].balance == 10000.0
    assert accounts[0].available == 9500.0


def test_client_cannot_place_orders() -> None:
    client = CapitalClient(make_broker_config(), CREDS, transport=FakeTransport([]))
    with pytest.raises(LiveTradingDisabledError):
        client.place_order(epic="US500", size=1.0, direction="BUY")
    with pytest.raises(LiveTradingDisabledError):
        client.create_position()
    with pytest.raises(LiveTradingDisabledError):
        client.close_position()
