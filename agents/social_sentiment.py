"""Social Sentiment Agent.

Responsible for social sentiment, most relevant for BTC and the broader macro
context. Its output is intentionally a *weak* signal:

- it can only slightly increase or decrease confidence (the Decision Agent
  weights it at 0.05);
- it can never open a trade by itself — the agent additionally bounds how far
  its score may move from neutral, and its relevance is dampened for
  non-crypto buckets;
- like every agent it cannot place orders.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from .base import BaseAgent, Signal

# Per-bucket relevance: sentiment matters most for crypto.
DEFAULT_BUCKET_RELEVANCE: dict[str, float] = {
    "crypto": 1.0,
    "equity_indices": 0.4,
    "metals": 0.3,
    "energy": 0.3,
}
DEFAULT_RELEVANCE = 0.3


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


@dataclass(frozen=True)
class SentimentSample:
    """A single social sentiment observation.

    ``sentiment`` is in ``[-1, 1]`` (bullish positive). ``weight`` lets louder
    sources (e.g. higher reach) count more.
    """

    timestamp: datetime
    sentiment: float
    weight: float = 1.0


@dataclass(frozen=True)
class SentimentAssessment:
    bucket: str
    score: float
    raw_sentiment: float
    sample_count: int
    relevance: float

    # Structural invariant: this signal is always weak.
    is_weak: bool = True


class SocialSentimentAgent(BaseAgent):
    """Aggregate social sentiment into a bounded, weak score."""

    name = "social_sentiment"

    def __init__(
        self,
        lookback_minutes: int = 180,
        bucket_relevance: dict[str, float] | None = None,
        max_deviation: float = 0.5,
    ) -> None:
        self._lookback = timedelta(minutes=lookback_minutes)
        self._relevance = dict(bucket_relevance or DEFAULT_BUCKET_RELEVANCE)
        # The score can move at most this far from 0.5 before relevance damping.
        self._max_deviation = max_deviation

    def relevance_for(self, bucket: str) -> float:
        return self._relevance.get(bucket, DEFAULT_RELEVANCE)

    def assess(
        self, bucket: str, now: datetime, samples: Sequence[SentimentSample]
    ) -> SentimentAssessment:
        recent = [s for s in samples if (now - self._lookback) <= s.timestamp <= now]
        relevance = self.relevance_for(bucket)

        if not recent:
            return SentimentAssessment(bucket, 0.5, 0.0, 0, relevance)

        total_weight = sum(max(s.weight, 0.0) for s in recent)
        if total_weight <= 0:
            raw = 0.0
        else:
            raw = sum(s.sentiment * max(s.weight, 0.0) for s in recent) / total_weight
        raw = max(-1.0, min(1.0, raw))

        # Bounded, relevance-damped deviation from neutral.
        deviation = raw * self._max_deviation * relevance
        score = _clamp(0.5 + deviation)
        return SentimentAssessment(bucket, score, raw, len(recent), relevance)

    def analyze(self, context: dict[str, Any]) -> Signal:
        """Return a Signal carrying the (weak) sentiment score.

        ``context`` must contain ``bucket``; ``now`` and ``samples`` are optional.
        """

        assessment = self.assess(
            bucket=context["bucket"],
            now=context.get("now") or datetime.now(timezone.utc),
            samples=context.get("samples", ()),
        )
        return Signal(
            self.name,
            assessment.score,
            f"sentiment={assessment.raw_sentiment:+.2f} (weak)",
            metadata={
                "raw_sentiment": assessment.raw_sentiment,
                "relevance": assessment.relevance,
                "sample_count": assessment.sample_count,
                "is_weak": True,
            },
        )
