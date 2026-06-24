"""End-to-end pipeline tests: technical -> decision -> risk -> order."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agents.candles import Candle
from app.config import load_config
from app.modes import OperatingMode
from app.orchestrator import MarketSnapshot, Orchestrator, PipelineState
from backtesting.paper_simulator import PaperCFDSimulator
from capital.models import Price
from risk.models import Direction

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
NOW = datetime(2026, 1, 2, tzinfo=timezone.utc)


def candles(closes: list[float], step_min: int, last_volume: float | None = None):
    out = []
    for i, close in enumerate(closes):
        vol = 1000.0 if last_volume is None or i < len(closes) - 1 else last_volume
        out.append(
            Candle(BASE + timedelta(minutes=step_min * i), close, close + 1,
                   close - 1, close, vol)
        )
    return out


def uptrend_snapshot(symbol: str = "US500") -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol,
        candles_1h=candles([100.0 + i for i in range(60)], 60),
        candles_15m=candles([100.0 + i * 0.5 for i in range(40)], 15, last_volume=2000.0),
        price=Price(epic=symbol, bid=119.4, offer=119.6, timestamp=NOW),
        now=NOW,
    )


def make_orchestrator(mode: OperatingMode, *, with_sim: bool = True, **kw):
    config = load_config()
    sim = PaperCFDSimulator(starting_balance=10_000.0) if with_sim else None
    return Orchestrator(config, mode=mode, simulator=sim, starting_equity=10_000.0, **kw)


def test_shadow_pipeline_executes_simulated_fill() -> None:
    orch = make_orchestrator(OperatingMode.SHADOW)
    result = orch.run_symbol(uptrend_snapshot())

    assert result.decision.outcome.value == "TRADE_CANDIDATE"
    assert result.risk is not None and result.risk.approved
    assert result.state is PipelineState.EXECUTED
    assert result.order is not None and result.order.simulated_position is not None
    assert result.order.simulated_position.direction is Direction.LONG
    # audit trail captured the run
    assert any(r.get("stage") == "executed" for r in orch.audit_log)


def test_capital_demo_is_read_only() -> None:
    # approved trade but no execution in read-only mode
    orch = make_orchestrator(OperatingMode.CAPITAL_DEMO, with_sim=False)
    result = orch.run_symbol(uptrend_snapshot())

    assert result.risk is not None and result.risk.approved
    assert result.state is PipelineState.READONLY_SKIPPED
    assert result.order is None


def test_sideways_results_in_no_trade() -> None:
    orch = make_orchestrator(OperatingMode.SHADOW)
    flat = [100.0 + (1.0 if i % 2 else -1.0) for i in range(60)]
    snap = MarketSnapshot(
        symbol="US500",
        candles_1h=candles(flat, 60),
        candles_15m=candles(flat[:40], 15),
        price=Price("US500", 99.9, 100.1, NOW),
        now=NOW,
    )
    result = orch.run_symbol(snap)
    assert result.state is PipelineState.NO_TRADE
    assert result.risk is None


def test_news_conflict_forces_wait() -> None:
    orch = make_orchestrator(OperatingMode.SHADOW)
    snap = MarketSnapshot(
        symbol="US500",
        candles_1h=uptrend_snapshot().candles_1h,
        candles_15m=uptrend_snapshot().candles_15m,
        price=Price("US500", 119.4, 119.6, NOW),
        news_conflict=True,
        now=NOW,
    )
    result = orch.run_symbol(snap)
    assert result.state is PipelineState.WAIT
    assert result.risk is None  # never reached risk stage


def test_high_spread_rejected_by_risk() -> None:
    orch = make_orchestrator(OperatingMode.SHADOW)
    snap = MarketSnapshot(
        symbol="US500",
        candles_1h=uptrend_snapshot().candles_1h,
        candles_15m=uptrend_snapshot().candles_15m,
        # huge spread overrides the price-derived one
        spread=50.0,
        price=Price("US500", 119.4, 119.6, NOW),
        now=NOW,
    )
    result = orch.run_symbol(snap)
    assert result.state is PipelineState.RISK_REJECTED
    assert result.risk is not None and not result.risk.approved


def test_audit_failure_blocks_trade() -> None:
    def failing_sink(record: dict) -> None:
        if record.get("stage") == "pre_trade":
            raise IOError("audit unavailable")

    orch = make_orchestrator(OperatingMode.SHADOW, audit_sink=failing_sink)
    result = orch.run_symbol(uptrend_snapshot())
    assert result.state is PipelineState.RISK_REJECTED
    assert result.proposal is not None and result.proposal.audit_log_ok is False


def test_bucket_limit_blocks_second_correlated_trade() -> None:
    orch = make_orchestrator(OperatingMode.SHADOW)
    # First US500 trade executes.
    first = orch.run_symbol(uptrend_snapshot("US500"))
    assert first.state is PipelineState.EXECUTED
    # NASDAQ is in the same equity_indices bucket -> blocked.
    nasdaq = MarketSnapshot(
        symbol="NASDAQ",
        candles_1h=candles([200.0 + i for i in range(60)], 60),
        candles_15m=candles([200.0 + i * 0.5 for i in range(40)], 15, last_volume=2000.0),
        price=Price("NASDAQ", 219.4, 219.6, NOW),
        now=NOW,
    )
    marks = {"US500": 119.5}
    result = orch.run_symbol(nasdaq, marks)
    assert result.state is PipelineState.RISK_REJECTED
    assert result.risk is not None
    assert any(r.value == "bucket_limit" for r in result.risk.reasons)
