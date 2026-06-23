"""Interface stubs for the remaining analysis agents.

These define the contracts for agents that will be implemented in later
milestones. Each returns a neutral signal for now. They are analysis-only and
cannot execute trades.

The Technical Analysis Agent is fully implemented in
:mod:`agents.technical_analysis`, the Market Data Agent in
:mod:`agents.market_data`, and the Daily Report Agent in
:mod:`agents.daily_report`.
"""

from __future__ import annotations

from typing import Any

from .base import BaseAgent, Signal


class NewsMacroAgent(BaseAgent):
    """Macro news, central banks, inflation, rates, employment, oil, geopolitics."""

    name = "news_macro"

    def analyze(self, context: dict[str, Any]) -> Signal:
        return Signal(self.name, 0.5, "stub: news/macro")


class SocialSentimentAgent(BaseAgent):
    """Social sentiment (esp. BTC). A weak signal that cannot open trades alone."""

    name = "social_sentiment"

    def analyze(self, context: dict[str, Any]) -> Signal:
        return Signal(self.name, 0.5, "stub: social sentiment (weak signal)")


class PortfolioAgent(BaseAgent):
    """Equity, PnL, open positions, exposure, margin, used risk, correlations."""

    name = "portfolio"

    def analyze(self, context: dict[str, Any]) -> Signal:
        return Signal(self.name, 0.5, "stub: portfolio fit")
