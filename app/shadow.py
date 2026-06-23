"""Shadow-trading runner.

Wires every agent into the Orchestrator and runs the full decision pipeline
across all configured symbols, producing a daily report. This is the glue that
shows the whole system end to end.

Data comes from an injectable :class:`ShadowDataSource`:

- :class:`CapitalDataSource` pulls live, read-only data from Capital.com;
- :class:`SyntheticDataSource` generates data for ``--demo`` and tests.

Strictly read-only / SHADOW: fills are simulated by the paper simulator and
nothing is ever sent to the broker.

Examples::

    python -m app.shadow --demo
    python -m app.shadow            # live read-only (needs Capital.com creds)
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol, Sequence

from agents.candles import Candle
from agents.daily_report import DailyReport, DailyReportAgent
from agents.llm_news import LLMNewsInterpreter
from agents.news_macro import MacroEvent, NewsMacroAgent
from agents.social_sentiment import SocialSentimentAgent
from app.ai_director import AIDirector
from app.config import AppConfig, load_config, load_news_config
from app.env import load_credentials
from app.errors import MissingCredentialsError, OrchestratorError
from app.logging_utils import configure_logging, get_logger
from app.modes import OperatingMode
from app.orchestrator import AuditSink, MarketSnapshot, Orchestrator, PipelineResult
from app.reporting import format_daily_report
from backtesting.paper_simulator import PaperCFDSimulator
from capital.models import Price

logger = get_logger("app.shadow")


class ShadowDataSource(Protocol):
    """Provides candles and the latest price for a symbol (read-only)."""

    def candles(self, symbol: str, timeframe: str, max_points: int) -> list[Candle]: ...

    def price(self, symbol: str) -> Price: ...


@dataclass
class ShadowRunReport:
    results: list[PipelineResult]
    report: DailyReport
    briefing: str | None = None

    def render(self) -> str:
        lines = [format_daily_report(self.report.as_dict()), "", "--- Per symbol ---"]
        for r in self.results:
            direction = r.technical.direction.value if r.technical.direction else "-"
            lines.append(
                f"  {r.symbol:<8} {r.state.value:<18} "
                f"score={r.decision.final_score:.3f} dir={direction}"
            )
        if self.briefing:
            lines.append("")
            lines.append("--- AI Director (advisory) ---")
            lines.append(self.briefing)
        return "\n".join(lines)


class ShadowRunner:
    """Runs the pipeline across symbols and builds a daily report."""

    def __init__(
        self,
        config: AppConfig,
        data_source: ShadowDataSource,
        *,
        symbols: Sequence[str] | None = None,
        starting_equity: float = 10_000.0,
        points_1h: int = 200,
        points_15m: int = 200,
        news_agent: NewsMacroAgent | None = None,
        sentiment_agent: SocialSentimentAgent | None = None,
        news_interpreter: LLMNewsInterpreter | None = None,
        ai_director: AIDirector | None = None,
        audit_sink: AuditSink | None = None,
    ) -> None:
        self._config = config
        self._source = data_source
        self._symbols = tuple(
            symbols or [i.symbol for i in config.instruments.instruments]
        )
        self._points_1h = points_1h
        self._points_15m = points_15m
        self._news_interpreter = news_interpreter
        self._ai_director = ai_director
        self._simulator = PaperCFDSimulator(starting_balance=starting_equity)
        self._orchestrator = Orchestrator(
            config,
            mode=OperatingMode.SHADOW,
            simulator=self._simulator,
            starting_equity=starting_equity,
            news_agent=news_agent,
            sentiment_agent=sentiment_agent,
            audit_sink=audit_sink,
        )

    def run(
        self, now: datetime | None = None, news_text: str = ""
    ) -> ShadowRunReport:
        now = now or datetime.now(timezone.utc)
        results: list[PipelineResult] = []
        marks: dict[str, float] = {}

        # Interpret free-text news into structured macro events (LLM, optional).
        # The News Macro Agent filters them per bucket, so attaching the full
        # set to every snapshot is correct.
        events: list[MacroEvent] = []
        if self._news_interpreter is not None and news_text.strip():
            events = self._news_interpreter.interpret(news_text, now)
            if events:
                logger.info("interpreted %d macro event(s) from news", len(events))

        for symbol in self._symbols:
            try:
                c1h = self._source.candles(symbol, "1H", self._points_1h)
                c15 = self._source.candles(symbol, "15m", self._points_15m)
                price = self._source.price(symbol)
            except OrchestratorError as exc:
                logger.warning("skipping %s: %s", symbol, exc)
                continue

            marks[symbol] = price.mid
            snapshot = MarketSnapshot(
                symbol=symbol, candles_1h=c1h, candles_15m=c15, price=price,
                macro_events=events, now=now,
            )
            results.append(self._orchestrator.run_symbol(snapshot, marks))

        account = {"equity": round(self._simulator.equity(marks), 2)}
        report = DailyReportAgent().build(
            results, report_date=now.date(), account=account
        )

        # Advisory briefing (LLM, optional; read-only).
        briefing: str | None = None
        if self._ai_director is not None:
            briefing = self._ai_director.brief(
                report.as_dict(), self._orchestrator.audit_log
            )

        return ShadowRunReport(results=results, report=report, briefing=briefing)


class CapitalDataSource:
    """Live, read-only data from the Capital.com client + Market Data Agent."""

    def __init__(self, config: AppConfig, client: Any, market_data_agent: Any) -> None:
        self._config = config
        self._client = client
        self._mda = market_data_agent

    def candles(self, symbol: str, timeframe: str, max_points: int) -> list[Candle]:
        return self._mda.candles(symbol, timeframe, max_points)

    def price(self, symbol: str) -> Price:
        epic = self._config.instruments.by_symbol(symbol).epic
        return self._client.get_latest_price(epic)


class SyntheticDataSource:
    """Deterministic synthetic data for ``--demo`` and tests (uptrends)."""

    BASES = {
        "US500": 5000.0, "NASDAQ": 18000.0, "GOLD": 2000.0,
        "USOIL": 75.0, "BTC": 60000.0,
    }

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def _base(self, symbol: str) -> float:
        return self.BASES.get(symbol, 1000.0)

    def candles(self, symbol: str, timeframe: str, max_points: int) -> list[Candle]:
        base = self._base(symbol)
        band = base * 0.001
        if timeframe == "1H":
            n, step_min, step = 60, 60, base * 0.001
        else:
            n, step_min, step = 40, 15, base * 0.0005
        out: list[Candle] = []
        for i in range(n):
            close = base + step * i
            vol = 2000.0 if i == n - 1 else 1000.0
            out.append(
                Candle(
                    timestamp=self._base_time + timedelta(minutes=step_min * i),
                    open=close, high=close + band, low=close - band, close=close,
                    volume=vol,
                )
            )
        return out

    def price(self, symbol: str) -> Price:
        base = self._base(symbol)
        last = base + base * 0.0005 * 39  # last 15m close
        half = base * 0.00005
        return Price(symbol, bid=last - half, offer=last + half,
                     timestamp=datetime.now(timezone.utc))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m app.shadow", description=__doc__)
    p.add_argument("--symbols", nargs="*", help="symbols to run (default: all)")
    p.add_argument("--balance", type=float, default=10_000.0)
    p.add_argument("--demo", action="store_true",
                   help="use synthetic data (no broker connection)")
    p.add_argument("--news", help="free-text news to interpret via the LLM")
    p.add_argument("--news-file", dest="news_file",
                   help="path to a file of news text to interpret")
    p.add_argument("--brief", action="store_true",
                   help="generate the AI Director advisory briefing")
    p.add_argument("--audit-file", dest="audit_file",
                   help="append the audit trail to this JSONL file")
    return p


def run(argv: list[str] | None = None) -> int:
    configure_logging()
    args = build_parser().parse_args(argv)
    config = load_config()
    logger.info("Shadow run in mode=SHADOW (read-only; no orders are sent)")

    if args.demo:
        source: ShadowDataSource = SyntheticDataSource(config)
    else:
        try:
            credentials = load_credentials(
                api_key_var=config.broker.api_key_var,
                identifier_var=config.broker.identifier_var,
                password_var=config.broker.password_var,
            )
        except MissingCredentialsError as exc:
            logger.error("%s", exc)
            logger.error("Set credentials (see .env.example) or use --demo.")
            return 2
        # Imported here so --demo needs no broker dependencies.
        from capital.client import CapitalClient
        from agents.market_data import MarketDataAgent

        client = CapitalClient(config.broker, credentials)
        client.login()
        source = CapitalDataSource(config, client, MarketDataAgent(config, client))

    # Optional LLM layer (deterministic offline mock without ANTHROPIC_API_KEY).
    from app.audit import JsonlAuditSink
    from app.llm import build_llm_client

    llm = build_llm_client()
    news_config = load_news_config()
    news_text = args.news or ""
    if args.news_file:
        with open(args.news_file, "r", encoding="utf-8") as handle:
            news_text = handle.read()

    runner = ShadowRunner(
        config,
        source,
        symbols=args.symbols,
        starting_equity=args.balance,
        news_agent=NewsMacroAgent(news_config),
        sentiment_agent=SocialSentimentAgent(),
        news_interpreter=LLMNewsInterpreter(llm, news_config),
        ai_director=AIDirector(llm) if args.brief else None,
        audit_sink=JsonlAuditSink(args.audit_file) if args.audit_file else None,
    )
    report = runner.run(news_text=news_text)
    print(report.render())
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(run())
