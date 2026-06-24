"""Tests for JSONL audit persistence and its pipeline integration."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agents.candles import Candle
from app.audit import JsonlAuditSink, load_audit_log
from app.config import load_config
from app.modes import OperatingMode
from app.orchestrator import MarketSnapshot, Orchestrator, PipelineState
from app.shadow import ShadowRunner, SyntheticDataSource
from backtesting.paper_simulator import PaperCFDSimulator
from capital.models import Price

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


# -- JsonlAuditSink --------------------------------------------------------


def test_sink_writes_and_reads_back(tmp_path) -> None:
    path = tmp_path / "logs" / "audit.jsonl"  # parent created automatically
    sink = JsonlAuditSink(path)
    sink({"symbol": "US500", "stage": "executed"})
    sink({"symbol": "GOLD", "stage": "risk_rejected"})

    records = load_audit_log(path)
    assert len(records) == 2
    assert records[0]["symbol"] == "US500"
    assert records[1]["stage"] == "risk_rejected"


def test_load_missing_file_returns_empty(tmp_path) -> None:
    assert load_audit_log(tmp_path / "nope.jsonl") == []


def test_sink_write_failure_raises(tmp_path) -> None:
    target = tmp_path / "audit.jsonl"
    target.mkdir()  # the target path is a directory -> append open fails
    sink = JsonlAuditSink(target)
    with pytest.raises(OSError):
        sink({"x": 1})


# -- pipeline integration --------------------------------------------------


def _candles(closes, step_min, last_volume=None):
    out = []
    for i, c in enumerate(closes):
        vol = 1000.0 if last_volume is None or i < len(closes) - 1 else last_volume
        out.append(
            Candle(BASE + timedelta(minutes=step_min * i), c, c + 1, c - 1, c, vol)
        )
    return out


def test_shadow_run_persists_audit(tmp_path) -> None:
    config = load_config()
    path = tmp_path / "audit.jsonl"
    runner = ShadowRunner(
        config, SyntheticDataSource(config), audit_sink=JsonlAuditSink(path),
    )
    runner.run(now=NOW)

    records = load_audit_log(path)
    assert len(records) > 0
    # the in-memory log is still populated (used by the AI Director)
    assert len(runner._orchestrator.audit_log) == len(records)  # noqa: SLF001
    assert all("symbol" in r for r in records)


def test_audit_failure_blocks_trade_via_jsonl(tmp_path) -> None:
    # Point the sink at a directory so every write raises -> the pre-trade
    # write fails and the Risk Engine rejects the trade.
    bad = tmp_path / "audit.jsonl"
    bad.mkdir()
    config = load_config()
    orch = Orchestrator(
        config, mode=OperatingMode.SHADOW, simulator=PaperCFDSimulator(10_000.0),
        starting_equity=10_000.0, audit_sink=JsonlAuditSink(bad),
    )
    snap = MarketSnapshot(
        symbol="US500",
        candles_1h=_candles([100.0 + i for i in range(60)], 60),
        candles_15m=_candles([100.0 + i * 0.5 for i in range(40)], 15, last_volume=2000.0),
        price=Price("US500", 119.4, 119.6, NOW),
        now=NOW,
    )
    result = orch.run_symbol(snap)
    assert result.state is PipelineState.RISK_REJECTED
    assert result.proposal is not None and result.proposal.audit_log_ok is False
