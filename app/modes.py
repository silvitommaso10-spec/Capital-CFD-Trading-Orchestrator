"""Operating modes for the orchestrator.

The system can run in several modes. Live trading is *never* a selectable mode
in this version: the only "live-adjacent" value is ``LIVE_DISABLED``, which
explicitly represents the disabled state and can never place real orders.
"""

from __future__ import annotations

from enum import Enum


class OperatingMode(str, Enum):
    """How the orchestrator interacts with the market.

    - ``BACKTEST``: replay historical data through the paper simulator.
    - ``SHADOW``: consume live read-only data, simulate decisions/fills, send
      nothing to the broker.
    - ``CAPITAL_DEMO``: read-only against the Capital.com demo API (the target
      of the first milestone). No orders are sent in this version.
    - ``LIVE_DISABLED``: explicit placeholder for live trading, which is hard
      disabled. Selecting it does not enable real orders.
    """

    BACKTEST = "BACKTEST"
    SHADOW = "SHADOW"
    CAPITAL_DEMO = "CAPITAL_DEMO"
    LIVE_DISABLED = "LIVE_DISABLED"


# The default mode is intentionally never LIVE.
DEFAULT_MODE: OperatingMode = OperatingMode.CAPITAL_DEMO

# Modes in which simulated fills are produced by the paper simulator.
SIMULATED_MODES = frozenset({OperatingMode.BACKTEST, OperatingMode.SHADOW})


def is_live_trading_enabled(mode: OperatingMode) -> bool:
    """Whether real broker orders may be sent.

    Always returns ``False`` in this version. Live trading is impossible to
    enable accidentally: there is no mode, config flag, or environment variable
    that flips this to ``True``.
    """

    return False


def parse_mode(value: str | None) -> OperatingMode:
    """Parse a mode string, falling back to the safe default.

    Unknown or empty values resolve to :data:`DEFAULT_MODE` rather than raising,
    so a misconfiguration can never silently escalate privileges.
    """

    if not value:
        return DEFAULT_MODE
    try:
        return OperatingMode(value.strip().upper())
    except ValueError:
        return DEFAULT_MODE
