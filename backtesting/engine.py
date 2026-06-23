"""Historical backtest engine.

Replays 1H and 15m candles through the decision pipeline, manages position
exits (stop loss / take profit) on the paper simulator, and reports
performance metrics.

Position *entries* come from the Orchestrator (Technical -> Decision -> Risk ->
Order Manager) exactly as in live/shadow operation. Position *exits* are the
engine's responsibility: on each new 15m bar it checks open positions against
their stop and target. This keeps the trading logic identical to production
while letting the backtest model the round trip.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import datetime
from typing import Sequence

from typing import TYPE_CHECKING

from agents.candles import Candle
from agents.decision_agent import DecisionAgent

if TYPE_CHECKING:
    from agents.market_data import MarketDataAgent
    from app.orchestrator import Orchestrator
from app.config import AppConfig
from app.modes import OperatingMode
from backtesting.paper_simulator import PaperCFDSimulator, SimulatedPosition
from capital.models import Price
from risk.models import Direction


@dataclass(frozen=True)
class Trade:
    symbol: str
    direction: Direction
    size: float
    entry_price: float
    exit_price: float
    pnl: float
    entry_time: datetime
    exit_time: datetime
    exit_reason: str  # "stop" | "target" | "end_of_data"

    @property
    def is_win(self) -> bool:
        return self.pnl > 0


@dataclass(frozen=True)
class BacktestMetrics:
    starting_balance: float
    final_equity: float
    net_pnl: float
    return_pct: float
    num_trades: int
    wins: int
    losses: int
    win_rate: float
    gross_profit: float
    gross_loss: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    expectancy: float
    max_drawdown_pct: float


@dataclass(frozen=True)
class BacktestResult:
    symbol: str
    trades: tuple[Trade, ...]
    equity_curve: tuple[tuple[datetime, float], ...]
    metrics: BacktestMetrics


@dataclass
class BacktestEngine:
    """Run a single-symbol backtest of the decision pipeline."""

    config: AppConfig
    starting_balance: float = 10_000.0
    assumed_spread: float = 0.0
    # Macro backdrop assumed for every bar (no News/Sentiment agents yet).
    news_score: float = 0.5
    sentiment_score: float = 0.5
    # Allow tuning the decision thresholds for experimentation.
    decision_agent: DecisionAgent | None = None
    # How many recent bars to feed the indicators each step.
    window: int = 250

    def run_from_data_agent(
        self,
        symbol: str,
        data_agent: "MarketDataAgent",
        points_1h: int = 300,
        points_15m: int = 300,
    ) -> BacktestResult:
        """Fetch candles via the Market Data Agent and run the backtest.

        This is the real-data path: the agent pulls OHLCV candles from the
        read-only Capital.com client. Read-only — no orders are sent.
        """

        candles_1h = data_agent.candles(symbol, "1H", points_1h)
        candles_15m = data_agent.candles(symbol, "15m", points_15m)
        return self.run(symbol, candles_1h, candles_15m)

    def run(
        self,
        symbol: str,
        candles_1h: Sequence[Candle],
        candles_15m: Sequence[Candle],
    ) -> BacktestResult:
        # Imported here to avoid a backtesting <-> app.orchestrator import cycle.
        from app.orchestrator import MarketSnapshot, Orchestrator, PipelineState

        simulator = PaperCFDSimulator(
            starting_balance=self.starting_balance, spread=self.assumed_spread
        )
        orch = Orchestrator(
            self.config,
            mode=OperatingMode.BACKTEST,
            simulator=simulator,
            starting_equity=self.starting_balance,
            decision_agent=self.decision_agent,
        )

        ts_1h = [c.timestamp for c in candles_1h]
        trend_slow = orch_trend_slow(orch)
        min_15m = 30  # enough warm-up for the 15m indicators

        trades: list[Trade] = []
        equity_curve: list[tuple[datetime, float]] = []
        open_pos: SimulatedPosition | None = None
        entry_time: datetime | None = None

        for i, bar in enumerate(candles_15m):
            # 1. Manage an open position against this bar.
            if open_pos is not None:
                exit_info = _check_exit(open_pos, bar)
                if exit_info is not None:
                    exit_price, reason = exit_info
                    pnl = simulator.close_position(open_pos.position_id, exit_price)
                    trades.append(
                        Trade(
                            symbol=symbol,
                            direction=open_pos.direction,
                            size=open_pos.size,
                            entry_price=open_pos.entry_price,
                            exit_price=exit_price,
                            pnl=pnl,
                            entry_time=entry_time or bar.timestamp,
                            exit_time=bar.timestamp,
                            exit_reason=reason,
                        )
                    )
                    open_pos = None
                    entry_time = None

            # 2. Look for a new entry (only when flat).
            n1h = bisect_right(ts_1h, bar.timestamp)
            if (
                open_pos is None
                and n1h >= trend_slow + 1
                and i + 1 >= min_15m
            ):
                window_1h = candles_1h[max(0, n1h - self.window) : n1h]
                window_15m = candles_15m[max(0, i + 1 - self.window) : i + 1]
                half = self.assumed_spread / 2.0
                snap = MarketSnapshot(
                    symbol=symbol,
                    candles_1h=window_1h,
                    candles_15m=window_15m,
                    price=Price(symbol, bar.close - half, bar.close + half, bar.timestamp),
                    news_score=self.news_score,
                    sentiment_score=self.sentiment_score,
                    spread=self.assumed_spread,
                    data_age_seconds=0.0,
                    now=bar.timestamp,
                )
                result = orch.run_symbol(snap, marks={symbol: bar.close})
                if result.state is PipelineState.EXECUTED and result.order is not None:
                    open_pos = result.order.simulated_position
                    entry_time = bar.timestamp

            equity_curve.append((bar.timestamp, simulator.equity({symbol: bar.close})))

        # 3. Close any position still open at the end of the data.
        if open_pos is not None and candles_15m:
            last = candles_15m[-1]
            pnl = simulator.close_position(open_pos.position_id, last.close)
            trades.append(
                Trade(
                    symbol=symbol,
                    direction=open_pos.direction,
                    size=open_pos.size,
                    entry_price=open_pos.entry_price,
                    exit_price=last.close,
                    pnl=pnl,
                    entry_time=entry_time or last.timestamp,
                    exit_time=last.timestamp,
                    exit_reason="end_of_data",
                )
            )

        metrics = self._metrics(trades, equity_curve)
        return BacktestResult(
            symbol=symbol,
            trades=tuple(trades),
            equity_curve=tuple(equity_curve),
            metrics=metrics,
        )

    def _metrics(
        self,
        trades: Sequence[Trade],
        equity_curve: Sequence[tuple[datetime, float]],
    ) -> BacktestMetrics:
        wins = [t for t in trades if t.is_win]
        losses = [t for t in trades if not t.is_win]
        gross_profit = sum(t.pnl for t in wins)
        gross_loss = abs(sum(t.pnl for t in losses))
        net_pnl = sum(t.pnl for t in trades)
        num = len(trades)

        profit_factor = (
            gross_profit / gross_loss
            if gross_loss > 0
            else (float("inf") if gross_profit > 0 else 0.0)
        )
        final_equity = self.starting_balance + net_pnl
        return BacktestMetrics(
            starting_balance=self.starting_balance,
            final_equity=final_equity,
            net_pnl=net_pnl,
            return_pct=net_pnl / self.starting_balance if self.starting_balance else 0.0,
            num_trades=num,
            wins=len(wins),
            losses=len(losses),
            win_rate=len(wins) / num if num else 0.0,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            profit_factor=profit_factor,
            avg_win=gross_profit / len(wins) if wins else 0.0,
            avg_loss=-gross_loss / len(losses) if losses else 0.0,
            expectancy=net_pnl / num if num else 0.0,
            max_drawdown_pct=_max_drawdown([e for _, e in equity_curve]),
        )


def orch_trend_slow(orch: Orchestrator) -> int:
    """Read the slow trend period from the orchestrator's technical agent."""

    return orch._technical._cfg.trend_slow  # noqa: SLF001 - internal read by design


def _check_exit(pos: SimulatedPosition, bar: Candle) -> tuple[float, str] | None:
    """Return (exit_price, reason) if the bar hits the stop or target.

    When both could trigger within a bar, the stop is assumed hit first
    (pessimistic / conservative).
    """

    if pos.direction is Direction.LONG:
        if pos.stop_loss is not None and bar.low <= pos.stop_loss:
            return pos.stop_loss, "stop"
        if pos.take_profit is not None and bar.high >= pos.take_profit:
            return pos.take_profit, "target"
    else:
        if pos.stop_loss is not None and bar.high >= pos.stop_loss:
            return pos.stop_loss, "stop"
        if pos.take_profit is not None and bar.low <= pos.take_profit:
            return pos.take_profit, "target"
    return None


def _max_drawdown(equity: Sequence[float]) -> float:
    """Maximum peak-to-trough drawdown as a positive fraction (0.0..1.0)."""

    peak = float("-inf")
    max_dd = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            dd = (peak - value) / peak
            max_dd = max(max_dd, dd)
    return max_dd
