"""Analysis agents.

Agents produce signals, scores and analysis only. They never execute trades:
order placement is the exclusive responsibility of the Order Manager, and
every trade must first be approved by the Risk Engine.
"""

from .base import BaseAgent, Signal
from .decision_agent import Decision, DecisionAgent, DecisionOutcome, ScoreInputs

__all__ = [
    "BaseAgent",
    "Signal",
    "DecisionAgent",
    "Decision",
    "DecisionOutcome",
    "ScoreInputs",
]
