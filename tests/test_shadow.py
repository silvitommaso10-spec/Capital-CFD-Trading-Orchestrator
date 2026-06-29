"""Tests for the shadow-trading runner."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from agents.candles import Candle
from agents.llm_news import LLMNewsInterpreter
from agents.news_macro import NewsMacroAgent
from app.ai_director import AIDirector
from app.config import load_config, load_news_config
from app.errors import MarketNotFoundError
from app.llm import MockLLMClient
from app.orchestrator import PipelineState
from app import shadow as shadow_cli
from app.shadow import (
    ShadowRunner,
    SyntheticDataSource,
    load_simulator_state,
)
from backtesting.paper_simulator import PaperCFDSimulator
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


# -- LLM integration -------------------------------------------------------


def test_interpreted_news_blackout_forces_wait() -> None:
    config = load_config()
    news_config = load_news_config()
    # The LLM (mocked) extracts a high-impact central-bank event -> blackout.
    payload = json.dumps({"events": [
        {"category": "central_bank", "sentiment": 0.0, "impact": "high",
         "confirmed": True, "title": "FOMC decision"},
    ]})
    runner = ShadowRunner(
        config, SyntheticDataSource(config),
        news_agent=NewsMacroAgent(news_config),
        news_interpreter=LLMNewsInterpreter(MockLLMClient(canned=payload), news_config),
    )
    run = runner.run(now=NOW, news_text="The FOMC announced its decision today.")
    states = {r.symbol: r.state for r in run.results}

    # central_bank affects equity_indices -> US500 waits during the blackout
    assert states["US500"] is PipelineState.WAIT
    # energy is unaffected by central_bank news -> USOIL still trades
    assert states["USOIL"] is PipelineState.EXECUTED


def test_no_news_text_means_no_events() -> None:
    config = load_config()
    news_config = load_news_config()
    runner = ShadowRunner(
        config, SyntheticDataSource(config),
        news_agent=NewsMacroAgent(news_config),
        news_interpreter=LLMNewsInterpreter(MockLLMClient(canned="{}"), news_config),
    )
    run = runner.run(now=NOW, news_text="")  # no news -> interpreter not called
    states = {r.symbol: r.state for r in run.results}
    assert states["US500"] is PipelineState.EXECUTED


def test_ai_director_briefing_in_report() -> None:
    config = load_config()
    runner = ShadowRunner(
        config, SyntheticDataSource(config),
        ai_director=AIDirector(MockLLMClient(canned="All decisions look sound.")),
    )
    run = runner.run(now=NOW)
    assert run.briefing == "All decisions look sound."
    assert "AI Director" in run.render()


def test_cli_loop_runs_multiple_cycles(tmp_path, capsys) -> None:
    audit = tmp_path / "audit.jsonl"
    dash = tmp_path / "hud.html"
    rc = shadow_cli.run([
        "--demo", "--interval", "0", "--iterations", "2",
        "--audit-file", str(audit), "--dashboard", str(dash),
    ])
    assert rc == 0
    # Both cycles ran and each produced per-symbol output.
    out = capsys.readouterr().out
    assert out.count("Per symbol") == 2
    # Dashboard refreshed and audit trail appended across cycles.
    assert dash.exists()
    assert audit.exists() and audit.read_text(encoding="utf-8").strip()
    # Loop mode embeds a browser auto-refresh in the HUD.
    assert "http-equiv='refresh'" in dash.read_text(encoding="utf-8")


def test_cli_single_run_has_no_auto_refresh(tmp_path) -> None:
    dash = tmp_path / "hud.html"
    rc = shadow_cli.run(["--demo", "--dashboard", str(dash)])
    assert rc == 0
    assert "http-equiv='refresh'" not in dash.read_text(encoding="utf-8")


def test_cli_state_file_persists_positions_across_restarts(tmp_path) -> None:
    state = tmp_path / "paper.json"

    # First process: opens paper positions and saves the account.
    rc = shadow_cli.run([
        "--demo", "--interval", "0", "--iterations", "1",
        "--state-file", str(state),
    ])
    assert rc == 0
    assert state.exists()
    sim_before = PaperCFDSimulator.from_dict(json.loads(state.read_text()))
    assert len(sim_before.open_positions) >= 1

    # Second process: restores the account; positions carry forward, so the
    # same symbols are now rejected as already-open instead of re-executed.
    runner = ShadowRunner(
        load_config(),
        SyntheticDataSource(load_config()),
        simulator=load_simulator_state(str(state), 10_000.0),
    )
    run = runner.run(now=NOW)
    states = {r.symbol: r.state for r in run.results}
    assert states["US500"] is PipelineState.RISK_REJECTED
