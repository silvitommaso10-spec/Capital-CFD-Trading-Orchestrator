"""Tests for the historical backtest engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agents.candles import Candle
from agents.decision_agent import DecisionAgent
from app.config import load_config
from backtesting.engine import BacktestEngine, _max_drawdown

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def build_series(
    n: int, start: float, step: float, step_min: int, band: float = 1.0,
    volume: float = 1000.0,
) -> list[Candle]:
    out = []
    for i in range(n):
        close = start + step * i
        out.append(
            Candle(
                timestamp=BASE + timedelta(minutes=step_min * i),
                open=close,
                high=close + band,
                low=close - band,
                close=close,
                volume=volume,
            )
        )
    return out


def test_max_drawdown_simple() -> None:
    # peak 120 then trough 90 -> dd = 30/120 = 0.25
    assert _max_drawdown([100, 120, 90, 110]) == 0.25
    assert _max_drawdown([100, 101, 102]) == 0.0


def test_uptrend_backtest_produces_winning_trades() -> None:
    config = load_config()
    # 80 hours of data: 1H bars and the aligned 4x 15m bars, both trending up.
    candles_1h = build_series(80, start=100.0, step=1.0, step_min=60)
    candles_15m = build_series(320, start=100.0, step=0.25, step_min=15)

    engine = BacktestEngine(
        config,
        starting_balance=10_000.0,
        assumed_spread=0.2,
        # Lower thresholds so the engine's trade lifecycle is exercised
        # deterministically on synthetic data.
        decision_agent=DecisionAgent(trade_threshold=0.5, watchlist_threshold=0.4),
    )
    result = engine.run("US500", candles_1h, candles_15m)

    m = result.metrics
    assert m.num_trades >= 1
    assert m.wins >= 1
    assert m.net_pnl > 0
    assert m.final_equity > m.starting_balance
    assert m.win_rate > 0.0
    assert 0.0 <= m.max_drawdown_pct <= 1.0
    # every trade in a clean uptrend should exit on target or end-of-data
    assert all(t.exit_reason in ("target", "end_of_data") for t in result.trades)
    # equity curve recorded for every 15m bar
    assert len(result.equity_curve) == len(candles_15m)


def test_flat_market_makes_no_trades() -> None:
    config = load_config()
    flat = [100.0]
    candles_1h = [
        Candle(BASE + timedelta(minutes=60 * i), 100, 101, 99, 100, 1000.0)
        for i in range(80)
    ]
    candles_15m = [
        Candle(BASE + timedelta(minutes=15 * i), 100, 101, 99, 100, 1000.0)
        for i in range(320)
    ]
    engine = BacktestEngine(config, decision_agent=DecisionAgent(trade_threshold=0.5))
    result = engine.run("US500", candles_1h, candles_15m)

    assert result.metrics.num_trades == 0
    assert result.metrics.net_pnl == 0.0
    assert result.metrics.final_equity == 10_000.0
