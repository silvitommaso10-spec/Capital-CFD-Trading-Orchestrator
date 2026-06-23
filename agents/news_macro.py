"""News Macro Agent.

Responsible for macro news and economic events (central banks, inflation,
rates, employment, oil inventories, geopolitics, crypto regulation). It maps
events to the affected correlation buckets and produces, for a given bucket and
time:

- ``news_score`` — how supportive the macro backdrop is for the proposed
  direction (0..1, 0.5 = neutral);
- a *conflict* flag for contradictory, unconfirmed news;
- a *blackout* flag around imminent/just-passed high-impact events.

Analysis-only: it never places orders, and it can never open a trade by itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Sequence

from app.config import NewsConfig
from risk.models import Direction
from .base import BaseAgent, Signal


class Impact(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class MacroEvent:
    """A macro/economic event.

    ``sentiment`` is in ``[-1, 1]`` for the affected buckets: positive is
    risk-on / bullish, negative is risk-off / bearish, 0 is neutral.
    """

    timestamp: datetime
    category: str
    impact: Impact = Impact.MEDIUM
    sentiment: float = 0.0
    confirmed: bool = True
    title: str = ""


@dataclass(frozen=True)
class NewsAssessment:
    bucket: str
    news_score: float
    has_conflict: bool
    in_blackout: bool
    relevant_events: tuple[MacroEvent, ...]
    rationale: str

    @property
    def block(self) -> bool:
        """Whether opening a new trade should be paused (WAIT)."""

        return self.has_conflict or self.in_blackout


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


class NewsMacroAgent(BaseAgent):
    """Assess the macro backdrop for a correlation bucket."""

    name = "news_macro"

    def __init__(self, config: NewsConfig) -> None:
        self._cfg = config

    def affects_bucket(self, category: str, bucket: str) -> bool:
        return bucket in self._cfg.buckets_for_category(category)

    def assess(
        self,
        bucket: str,
        now: datetime,
        events: Sequence[MacroEvent],
        direction: Direction | None = None,
    ) -> NewsAssessment:
        lookback = timedelta(minutes=self._cfg.conflict_lookback_minutes)
        before = timedelta(minutes=self._cfg.high_impact_blackout_minutes_before)
        after = timedelta(minutes=self._cfg.high_impact_blackout_minutes_after)

        relevant = tuple(
            e for e in events if self.affects_bucket(e.category, bucket)
        )

        # Blackout: a high-impact event whose window contains `now`.
        in_blackout = any(
            e.impact is Impact.HIGH and (e.timestamp - before) <= now <= (e.timestamp + after)
            for e in relevant
        )

        # Recent events used for scoring/conflict (within the look-back window).
        recent = [e for e in relevant if (now - lookback) <= e.timestamp <= now]

        # Conflict: contradictory *unconfirmed* recent events (opposite signs).
        unconfirmed = [e for e in recent if not e.confirmed and e.sentiment != 0.0]
        has_pos = any(e.sentiment > 0 for e in unconfirmed)
        has_neg = any(e.sentiment < 0 for e in unconfirmed)
        has_conflict = has_pos and has_neg

        if in_blackout or has_conflict:
            reason = "blackout" if in_blackout else "conflicting_unconfirmed_news"
            return NewsAssessment(
                bucket=bucket,
                news_score=0.2,  # suppress confidence during uncertainty
                has_conflict=has_conflict,
                in_blackout=in_blackout,
                relevant_events=relevant,
                rationale=reason,
            )

        # Score from confirmed recent events, oriented by the trade direction.
        confirmed = [e for e in recent if e.confirmed]
        if confirmed:
            net = sum(e.sentiment for e in confirmed) / len(confirmed)
        else:
            net = 0.0
        orient = 1.0
        if direction is Direction.SHORT:
            orient = -1.0
        score = _clamp(0.5 + 0.5 * net * orient)

        return NewsAssessment(
            bucket=bucket,
            news_score=score,
            has_conflict=False,
            in_blackout=False,
            relevant_events=relevant,
            rationale=f"net_sentiment={net:+.2f}",
        )

    def analyze(self, context: dict[str, Any]) -> Signal:
        """Return a Signal carrying the news score.

        ``context`` must contain ``bucket``, ``now`` and ``events``; ``direction``
        is optional.
        """

        assessment = self.assess(
            bucket=context["bucket"],
            now=context.get("now") or datetime.now(timezone.utc),
            events=context.get("events", ()),
            direction=context.get("direction"),
        )
        return Signal(
            self.name,
            assessment.news_score,
            assessment.rationale,
            metadata={
                "has_conflict": assessment.has_conflict,
                "in_blackout": assessment.in_blackout,
                "block": assessment.block,
            },
        )
