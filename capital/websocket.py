"""Read-only price streaming over the Capital.com WebSocket.

Subscribes to market quote updates and forwards them to a callback. This is a
consumer only: it never sends trading instructions. ``websocket-client`` is an
optional dependency imported lazily so the rest of the package works without
it.
"""

from __future__ import annotations

import json
import threading
from typing import Callable, Iterable

from app.logging_utils import get_logger
from .auth import CapitalSession

logger = get_logger(__name__)

PriceCallback = Callable[[dict], None]


class PriceStream:
    """Subscribe to live quotes for a set of epics (read-only)."""

    def __init__(
        self,
        ws_url: str,
        session: CapitalSession,
        on_price: PriceCallback,
    ) -> None:
        self._ws_url = ws_url
        self._session = session
        self._on_price = on_price
        self._ws: object | None = None
        self._thread: threading.Thread | None = None
        self._epics: tuple[str, ...] = ()

    def _subscribe_message(self, epics: Iterable[str]) -> str:
        return json.dumps(
            {
                "destination": "marketData.subscribe",
                "correlationId": "1",
                "cst": self._session.cst,
                "securityToken": self._session.security_token,
                "payload": {"epics": list(epics)},
            }
        )

    def start(self, epics: Iterable[str]) -> None:
        """Open the WebSocket and subscribe to ``epics`` in a background thread."""

        try:
            import websocket  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "websocket-client is required for live price streaming"
            ) from exc

        self._epics = tuple(epics)

        def _on_open(ws: object) -> None:
            ws.send(self._subscribe_message(self._epics))  # type: ignore[attr-defined]
            logger.info("subscribed to %d epics", len(self._epics))

        def _on_message(ws: object, message: str) -> None:
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                logger.warning("dropping non-JSON ws message")
                return
            self._on_price(data)

        def _on_error(ws: object, error: object) -> None:
            logger.warning("websocket error: %s", error)

        self._ws = websocket.WebSocketApp(
            self._ws_url,
            on_open=_on_open,
            on_message=_on_message,
            on_error=_on_error,
        )
        self._thread = threading.Thread(
            target=self._ws.run_forever,  # type: ignore[attr-defined]
            name="capital-price-stream",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._ws is not None:
            try:
                self._ws.close()  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover - defensive
                pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
