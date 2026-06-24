# Project Specification — Capital CFD Trading Orchestrator

## Purpose

A Python system for automated CFD trading, built first for **backtesting**,
**shadow trading** and **demo trading**. **Live trading is not available in
this version and is disabled by default.**

## Candidate broker

Capital.com **Demo** API.

## Instruments

| Symbol | Description       | Bucket          |
|--------|-------------------|-----------------|
| US500  | S&P 500 index CFD | equity_indices  |
| NASDAQ | Nasdaq 100 CFD    | equity_indices  |
| GOLD   | Gold              | metals          |
| USOIL  | Crude oil (WTI)   | energy          |
| BTC    | Bitcoin           | crypto          |

Product type: **CFD**.

## Operating modes

- `BACKTEST` — replay historical data through the paper simulator.
- `SHADOW` — live read-only data, simulated decisions/fills, nothing sent to the broker.
- `CAPITAL_DEMO` — read-only against the Capital.com demo API (first milestone).
- `LIVE_DISABLED` — explicit placeholder for live trading, hard-disabled.

The default mode is `CAPITAL_DEMO` (or `SHADOW`), **never** live.

## Timeframes

- **1H** — main trend analysis.
- **15m** — entry/exit timing.

## Trading style

Intraday, with controlled scalping; long and short. Leverage is allowed only
when consistent with the maximum defined risk. Leverage is never an objective:
position size is derived from capital, stop loss, required margin and the
maximum risk per trade.

## Milestones

1. **Read-only integration with the Capital.com Demo API** (this version):
   configuration management, environment variables, demo login/session,
   account reading, market search, symbol mapping, market details, prices,
   price WebSocket, secure logging, error handling, full typing, base unit
   tests. **No orders implemented.**
2. Paper simulator + risk engine validation.
3. Shadow trading.
4. Demo trading.

## Fundamental constraint of the first version

The first version **cannot open, close, or modify orders**. It is strictly
read-only toward the broker and prepared for the later phases.

## Repository structure

```
app/            # core: config, env, modes, logging, errors, entry point
agents/         # analysis agents (signals/scores only)
execution/      # Order Manager (only authorized order path)
capital/        # Capital.com read-only integration
risk/           # deterministic risk engine + margin calculator
backtesting/    # paper CFD simulator
data/           # local data/cache (later)
dashboard/      # dashboard/reporting (later)
monitoring/     # monitoring/alerting (later)
config/         # broker/risk/instruments/news/strategy YAML
tests/          # unit tests
docs/           # documentation
```

## Documentation index

- `docs/PROJECT_SPEC.md` (this file)
- `docs/ARCHITECTURE.md`
- `docs/RISK_POLICY.md`
- `docs/CFD_TRADING_SPEC.md`
- `docs/CAPITAL_COM_INTEGRATION.md`
- `docs/STRATEGY_SPEC.md`
