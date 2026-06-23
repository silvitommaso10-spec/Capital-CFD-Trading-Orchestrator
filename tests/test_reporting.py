"""Tests for CSV loading, the Daily Report Agent and report formatting."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from agents.candles import Candle
from agents.daily_report import DailyReportAgent
from agents.decision_agent import Decision, DecisionOutcome
from agents.technical_analysis import TechnicalSignal, Trend
from app.config import load_config
from app.modes import OperatingMode
from app.orchestrator import PipelineResult, PipelineState
from app.reporting import format_backtest_report, format_daily_report
from backtesting.engine import BacktestEngine
from backtesting.paper_simulator import SimulatedPosition
from data.csv_loader import parse_rows
from execution.order_manager import OrderResult
from risk.models import Direction

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


# -- CSV loader ------------------------------------------------------------


def test_parse_rows_iso_and_epoch() -> None:
    rows = [
        {"timestamp": "2026-01-01T00:00:00Z", "open": "100", "high": "101",
         "low": "99", "close": "100.5", "volume": "1000"},
        {"timestamp": "1767225600", "open": "100.5", "high": "102",
         "low": "100", "close": "101", "volume": "1500"},
    ]
    candles = parse_rows(rows)
    assert len(candles) == 2
    assert candles[0].open == 100.0
    assert candles[0].close == 100.5
    assert candles[0].volume == 1000.0
    # sorted by timestamp ascending
    assert candles[0].timestamp <= candles[1].timestamp


def test_parse_rows_volume_optional() -> None:
    rows = [{"timestamp": "2026-01-01T00:00:00Z", "open": "1", "high": "2",
             "low": "0.5", "close": "1.5"}]
    candles = parse_rows(rows)
    assert candles[0].volume == 0.0


# -- Daily Report Agent ----------------------------------------------------


def _signal() -> TechnicalSignal:
    return TechnicalSignal(
        symbol="US500", trend=Trend.UP, direction=Direction.LONG,
        trend_score=1.0, technical_score=0.8, volume_score=0.9,
    )


def _executed_result() -> PipelineResult:
    pos = SimulatedPosition(
        position_id=1, symbol="US500", direction=Direction.LONG, size=2.0,
        entry_price=5000.0, contract_size=1.0, margin_factor=0.05,
    )
    order = OrderResult(accepted=True, mode=OperatingMode.SHADOW, detail="paper fill",
                        simulated_position=pos)
    return PipelineResult(
        symbol="US500", state=PipelineState.EXECUTED, technical=_signal(),
        decision=Decision(DecisionOutcome.TRADE_CANDIDATE, 0.8, ""), order=order,
    )


def _no_trade_result() -> PipelineResult:
    return PipelineResult(
        symbol="NASDAQ", state=PipelineState.NO_TRADE,
        technical=TechnicalSignal("NASDAQ", Trend.SIDEWAYS, None, 0.0, 0.0, 0.0),
        decision=Decision(DecisionOutcome.NO_TRADE, 0.4, ""),
    )


def test_daily_report_counts_and_executed() -> None:
    agent = DailyReportAgent()
    report = agent.build(
        [_executed_result(), _no_trade_result()],
        report_date=date(2026, 6, 22),
    )
    assert report.total == 2
    assert report.by_state["EXECUTED"] == 1
    assert report.by_state["NO_TRADE"] == 1
    assert len(report.executed) == 1
    assert report.executed[0]["symbol"] == "US500"
    assert report.executed[0]["direction"] == "LONG"
    assert report.date == "2026-06-22"


def test_format_daily_report_text() -> None:
    agent = DailyReportAgent()
    report = agent.build([_executed_result()], report_date="2026-06-22")
    text = format_daily_report(report.as_dict())
    assert "Daily Report: 2026-06-22" in text
    assert "EXECUTED" in text
    assert "US500" in text


# -- Backtest report formatting -------------------------------------------


def test_format_backtest_report_contains_metrics() -> None:
    config = load_config()

    def series(n: int, start: float, step: float, m: int) -> list[Candle]:
        return [
            Candle(BASE + timedelta(minutes=m * i), start + step * i,
                   start + step * i + 1, start + step * i - 1, start + step * i, 1000.0)
            for i in range(n)
        ]

    from agents.decision_agent import DecisionAgent

    engine = BacktestEngine(
        config, assumed_spread=0.2,
        decision_agent=DecisionAgent(trade_threshold=0.5, watchlist_threshold=0.4),
    )
    result = engine.run("US500", series(80, 100, 1.0, 60), series(320, 100, 0.25, 15))
    text = format_backtest_report(result)

    assert "Backtest Report: US500" in text
    assert "Net PnL:" in text
    assert "Trades:" in text
    assert "Max drawdown:" in text
