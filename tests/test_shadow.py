"""Tests for the shadow-trading runner."""

from __future__ import annotations

from datetime import datetime, timezone

from agents.candles import Candle
from app.config import load_config
from app.errors import MarketNotFoundError
from app.orchestrator import PipelineState
from app.shadow import ShadowRunner, SyntheticDataSource
from capital.models import Price

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def test_synthetic_run_evaluates_all_symbols() -> None:
    config = load_config()
    runner = ShadowRunner(config, SyntheticDataSource(config))
    run = runner.run(now=NOW)

    symbols = [i.symbol for i in config.instruments.instruments]
    assert len(run.results) == len(symbols)
    assert run.report.total == len(symbols)
    # state counts sum to the number of symbols
    assert sum(run.report.by_state.values()) == len(symbols)
    assert run.report.account is not None and "equity" in run.report.account


def test_synthetic_run_executes_and_respects_bucket_limit() -> None:
    config = load_config()
    runner = ShadowRunner(config, SyntheticDataSource(config))
    run = runner.run(now=NOW)
    states = {r.symbol: r.state for r in run.results}

    # US500 fills; NASDAQ shares the equity_indices bucket -> blocked.
    assert states["US500"] is PipelineState.EXECUTED
    assert states["NASDAQ"] is PipelineState.RISK_REJECTED
    assert run.report.by_state["EXECUTED"] >= 1


def test_render_contains_report_and_per_symbol() -> None:
    config = load_config()
    runner = ShadowRunner(config, SyntheticDataSource(config))
    text = runner.run(now=NOW).render()
    assert "Daily Report" in text
    assert "Per symbol" in text
    assert "US500" in text


class _PartialSource:
    """Wraps the synthetic source but fails for one symbol."""

    def __init__(self, config) -> None:
        self._inner = SyntheticDataSource(config)

    def candles(self, symbol: str, timeframe: str, max_points: int) -> list[Candle]:
        if symbol == "BTC":
            raise MarketNotFoundError("no data for BTC")
        return self._inner.candles(symbol, timeframe, max_points)

    def price(self, symbol: str) -> Price:
        return self._inner.price(symbol)


def test_runner_skips_symbols_with_missing_data() -> None:
    config = load_config()
    runner = ShadowRunner(config, _PartialSource(config))
    run = runner.run(now=NOW)
    symbols = {r.symbol for r in run.results}
    assert "BTC" not in symbols
    assert "US500" in symbols
