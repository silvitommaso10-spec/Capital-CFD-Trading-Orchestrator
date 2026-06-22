"""Backtesting and paper trading."""

from .engine import (
    BacktestEngine,
    BacktestMetrics,
    BacktestResult,
    Trade,
)
from .paper_simulator import PaperCFDSimulator, SimulatedPosition

__all__ = [
    "PaperCFDSimulator",
    "SimulatedPosition",
    "BacktestEngine",
    "BacktestResult",
    "BacktestMetrics",
    "Trade",
]
