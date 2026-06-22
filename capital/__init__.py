"""Read-only Capital.com demo API integration.

This package is strictly read-only in this version: it can authenticate, read
the account, search markets, read market details and prices, and stream prices
over WebSocket. It contains no code path that opens, closes, or modifies
orders or positions.
"""

from .auth import CapitalSession
from .client import CapitalClient
from .mapper import MarketMapper
from .models import Account, MarketDetails, MarketSummary, Price

__all__ = [
    "CapitalClient",
    "CapitalSession",
    "MarketMapper",
    "Account",
    "MarketDetails",
    "MarketSummary",
    "Price",
]
