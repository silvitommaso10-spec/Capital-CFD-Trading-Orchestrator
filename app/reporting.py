"""Human-readable report rendering for backtests and daily summaries."""

from __future__ import annotations

from typing import Any

from backtesting.engine import BacktestResult


def _money(x: float) -> str:
    return f"{x:+,.2f}"


def format_backtest_report(result: BacktestResult, max_trades: int = 20) -> str:
    """Render a backtest result as a plain-text report."""

    m = result.metrics
    lines: list[str] = []
    lines.append(f"=== Backtest Report: {result.symbol} ===")

    if result.equity_curve:
        first = result.equity_curve[0][0]
        last = result.equity_curve[-1][0]
        lines.append(f"Period:           {first.isoformat()} -> {last.isoformat()}")
        lines.append(f"Bars:             {len(result.equity_curve)}")

    lines.append(f"Starting balance: {m.starting_balance:,.2f}")
    lines.append(f"Final equity:     {m.final_equity:,.2f}")
    lines.append(f"Net PnL:          {_money(m.net_pnl)} ({m.return_pct:+.2%})")
    lines.append(
        f"Trades:           {m.num_trades}  "
        f"(W {m.wins} / L {m.losses}, win rate {m.win_rate:.1%})"
    )
    pf = "inf" if m.profit_factor == float("inf") else f"{m.profit_factor:.2f}"
    lines.append(f"Profit factor:    {pf}")
    lines.append(f"Avg win / loss:   {_money(m.avg_win)} / {_money(m.avg_loss)}")
    lines.append(f"Expectancy:       {_money(m.expectancy)} per trade")
    lines.append(f"Max drawdown:     {m.max_drawdown_pct:.2%}")

    if result.trades:
        lines.append("--- Trades ---")
        for i, t in enumerate(result.trades[:max_trades], start=1):
            lines.append(
                f"{i:>3} {t.direction.value:<5} "
                f"{t.entry_price:,.2f} -> {t.exit_price:,.2f}  "
                f"{_money(t.pnl):>12}  {t.exit_reason}"
            )
        if len(result.trades) > max_trades:
            lines.append(f"    ... {len(result.trades) - max_trades} more")

    return "\n".join(lines)


def format_daily_report(report: dict[str, Any]) -> str:
    """Render a daily report dict (from the Daily Report Agent) as text."""

    lines: list[str] = []
    lines.append(f"=== Daily Report: {report.get('date', '')} ===")
    lines.append(f"Symbols evaluated: {report.get('total', 0)}")

    by_state = report.get("by_state", {})
    for state, count in by_state.items():
        lines.append(f"  {state:<18} {count}")

    executed = report.get("executed", [])
    if executed:
        lines.append("--- Executed ---")
        for item in executed:
            lines.append(
                f"  {item['symbol']:<8} {item.get('direction', ''):<5} "
                f"size={item.get('size', 0)}"
            )

    account = report.get("account")
    if account:
        lines.append("--- Account ---")
        lines.append(f"  equity={account.get('equity')}")

    return "\n".join(lines)
