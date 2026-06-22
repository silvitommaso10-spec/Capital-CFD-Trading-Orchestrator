"""Interface stubs for the remaining analysis agents.

These define the contracts for agents that will be implemented in later
milestones. Each returns a neutral signal for now. They are analysis-only and
cannot execute trades.

The Technical Analysis Agent is fully implemented in
:mod:`agents.technical_analysis`.
"""

from __future__ import annotations

from typing import Any

from .base import BaseAgent, Signal


class MarketDataAgent(BaseAgent):
    """Prices, candles, spread, volume, timestamps and data-quality flags."""

    name = "market_data"

    def analyze(self, context: dict[str, Any]) -> Signal:
        return Signal(self.name, 0.5, "stub: market data quality")


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


class DailyReportAgent:
    """Builds the daily report for the dashboard and email (later milestone)."""

    name = "daily_report"

    def build_report(self, context: dict[str, Any]) -> dict[str, Any]:
        return {"status": "stub", "context_keys": sorted(context)}
