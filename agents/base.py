"""Base agent abstractions.

An agent consumes data and emits a :class:`Signal` (a bounded score plus
metadata). Agents are pure analysis components; they cannot place, modify, or
cancel orders.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Signal:
    """A normalized agent output.

    ``score`` is clamped to the inclusive range ``[0.0, 1.0]``.
    """

    name: str
    score: float
    rationale: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        clamped = max(0.0, min(1.0, self.score))
        if clamped != self.score:
            object.__setattr__(self, "score", clamped)


class BaseAgent(abc.ABC):
    """Abstract base class for analysis agents."""

    name: str = "agent"

    @abc.abstractmethod
    def analyze(self, context: dict[str, Any]) -> Signal:
        """Return a :class:`Signal` for the given context."""

    # Agents must never execute. This guard makes accidental misuse explicit.
    def execute(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover
        raise NotImplementedError(
            "Agents do not execute trades; use the Order Manager via the "
            "Risk Engine."
        )
