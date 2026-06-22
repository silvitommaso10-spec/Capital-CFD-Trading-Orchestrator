"""Decision Agent.

Combines the component scores into a final score using the configured weights
and maps it to a decision. The Decision Agent only proposes (trade candidate,
watchlist, or no trade); it does not execute and it does not override the Risk
Engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DecisionOutcome(str, Enum):
    TRADE_CANDIDATE = "TRADE_CANDIDATE"
    WATCHLIST = "WATCHLIST"
    NO_TRADE = "NO_TRADE"
    WAIT = "WAIT"


# Scoring weights from the initial multi-confirmation strategy. They sum to 1.0.
WEIGHTS = {
    "technical": 0.40,
    "trend": 0.20,
    "volume": 0.15,
    "news": 0.15,
    "sentiment": 0.05,
    "portfolio_fit": 0.05,
}

TRADE_CANDIDATE_THRESHOLD = 0.72
WATCHLIST_THRESHOLD = 0.60

# The sentiment signal can only nudge confidence by this much (weak signal).
MAX_SENTIMENT_ADJUSTMENT = WEIGHTS["sentiment"]


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


@dataclass(frozen=True)
class ScoreInputs:
    """Component scores in ``[0, 1]`` plus hard gates."""

    technical_score: float
    trend_score: float
    volume_score: float
    news_score: float
    sentiment_score: float
    portfolio_fit_score: float
    # Hard gates evaluated before scoring.
    news_conflict: bool = False
    risk_rejected: bool = False


@dataclass(frozen=True)
class Decision:
    outcome: DecisionOutcome
    final_score: float
    rationale: str


class DecisionAgent:
    """Deterministic score aggregation and decision mapping."""

    def __init__(
        self,
        trade_threshold: float = TRADE_CANDIDATE_THRESHOLD,
        watchlist_threshold: float = WATCHLIST_THRESHOLD,
    ) -> None:
        self._trade_threshold = trade_threshold
        self._watchlist_threshold = watchlist_threshold

    def final_score(self, inputs: ScoreInputs) -> float:
        score = (
            _clamp(inputs.technical_score) * WEIGHTS["technical"]
            + _clamp(inputs.trend_score) * WEIGHTS["trend"]
            + _clamp(inputs.volume_score) * WEIGHTS["volume"]
            + _clamp(inputs.news_score) * WEIGHTS["news"]
            + _clamp(inputs.sentiment_score) * WEIGHTS["sentiment"]
            + _clamp(inputs.portfolio_fit_score) * WEIGHTS["portfolio_fit"]
        )
        return round(score, 6)

    def decide(self, inputs: ScoreInputs) -> Decision:
        # Hard gates take precedence over the numeric score.
        if inputs.news_conflict:
            return Decision(
                DecisionOutcome.WAIT,
                self.final_score(inputs),
                "Conflicting unconfirmed news: waiting.",
            )
        if inputs.risk_rejected:
            return Decision(
                DecisionOutcome.NO_TRADE,
                self.final_score(inputs),
                "Risk Engine rejected the trade.",
            )

        score = self.final_score(inputs)
        if score >= self._trade_threshold:
            outcome = DecisionOutcome.TRADE_CANDIDATE
        elif score >= self._watchlist_threshold:
            outcome = DecisionOutcome.WATCHLIST
        else:
            outcome = DecisionOutcome.NO_TRADE
        return Decision(outcome, score, f"final_score={score:.3f}")
