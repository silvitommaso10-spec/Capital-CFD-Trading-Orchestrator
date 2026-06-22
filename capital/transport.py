"""HTTP transport abstraction for the Capital.com client.

A thin, injectable layer so the client can be unit-tested without network
access. The default implementation wraps :mod:`requests`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from app.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class HttpResponse:
    """Normalized HTTP response."""

    status_code: int
    headers: Mapping[str, str] = field(default_factory=dict)
    json_body: Any = None
    text: str = ""

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


class Transport(Protocol):
    """Minimal transport interface used by :class:`CapitalClient`."""

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
        ...


class RequestsTransport:
    """Default transport backed by ``requests`` with simple retry/backoff."""

    def __init__(self, max_retries: int = 3, backoff_seconds: float = 2.0) -> None:
        import requests  # local import keeps requests optional for tests

        self._session = requests.Session()
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds

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
        import requests

        attempt = 0
        while True:
            attempt += 1
            try:
                resp = self._session.request(
                    method=method.upper(),
                    url=url,
                    headers=dict(headers or {}),
                    params=dict(params or {}),
                    json=json,
                    timeout=timeout,
                )
            except requests.RequestException as exc:
                if attempt > self._max_retries:
                    raise
                wait = self._backoff_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "transport error on %s %s (attempt %d): %s; retrying in %.1fs",
                    method,
                    url,
                    attempt,
                    exc,
                    wait,
                )
                time.sleep(wait)
                continue

            # Retry on transient server / rate-limit errors.
            if resp.status_code in (429, 500, 502, 503, 504) and attempt <= self._max_retries:
                wait = self._backoff_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "HTTP %d on %s %s (attempt %d); retrying in %.1fs",
                    resp.status_code,
                    method,
                    url,
                    attempt,
                    wait,
                )
                time.sleep(wait)
                continue

            try:
                body = resp.json()
            except ValueError:
                body = None
            return HttpResponse(
                status_code=resp.status_code,
                headers=dict(resp.headers),
                json_body=body,
                text=resp.text,
            )
