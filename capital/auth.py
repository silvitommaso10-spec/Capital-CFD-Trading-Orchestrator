"""Capital.com demo session / authentication (read-only)."""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.env import Credentials
from app.errors import AuthenticationError
from app.logging_utils import get_logger
from .transport import Transport

logger = get_logger(__name__)


@dataclass
class CapitalSession:
    """Holds the security tokens for an authenticated Capital.com session.

    The tokens (``cst`` and ``x-security-token``) are short-lived and never
    logged. ``__repr__`` is overridden to avoid leaking them.
    """

    cst: str
    security_token: str
    created_at: float
    ttl_seconds: float = 600.0

    def is_expired(self, refresh_margin_seconds: float = 60.0) -> bool:
        return (time.monotonic() - self.created_at) >= (
            self.ttl_seconds - refresh_margin_seconds
        )

    def auth_headers(self) -> dict[str, str]:
        return {"CST": self.cst, "X-SECURITY-TOKEN": self.security_token}

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return "CapitalSession(cst=***, security_token=***)"


def create_session(
    *,
    transport: Transport,
    base_url: str,
    credentials: Credentials,
    timeout: float = 15.0,
) -> CapitalSession:
    """Authenticate against ``POST /api/v1/session`` and return a session.

    Read-only: this only establishes a session; it never enables trading.
    """

    url = f"{base_url.rstrip('/')}/api/v1/session"
    headers = {
        "X-CAP-API-KEY": credentials.api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "identifier": credentials.identifier,
        "password": credentials.password,
    }

    resp = transport.request(
        "POST", url, headers=headers, json=payload, timeout=timeout
    )
    if not resp.ok:
        # Never include the payload/credentials in the error.
        raise AuthenticationError(
            f"Capital.com authentication failed with HTTP {resp.status_code}"
        )

    cst = resp.headers.get("CST") or resp.headers.get("cst")
    token = resp.headers.get("X-SECURITY-TOKEN") or resp.headers.get(
        "x-security-token"
    )
    if not cst or not token:
        raise AuthenticationError(
            "Authentication response missing session tokens"
        )

    logger.info("Capital.com demo session established")
    return CapitalSession(
        cst=cst, security_token=token, created_at=time.monotonic()
    )
