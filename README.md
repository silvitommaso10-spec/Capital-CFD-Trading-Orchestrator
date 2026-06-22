# Capital CFD Trading Orchestrator

A Python system for automated CFD trading research and execution, built first
for **backtesting**, **shadow trading** and **demo trading**.

> ⚠️ **Live trading is not available in this version and is disabled by
> default.** This first milestone is strictly **read-only** toward the broker:
> it cannot open, close, or modify any order.

## Status: Milestone 1 — read-only Capital.com demo integration

Implemented:

- Configuration management (`config/*.yaml`) and environment-variable handling.
- Capital.com **demo** session/login, account reading, market search, symbol
  mapping (US500, NASDAQ, GOLD, USOIL, BTC), market details, prices and a
  read-only price WebSocket.
- Deterministic **Risk Engine** and risk-first **Margin Calculator**.
- **Paper CFD simulator** for BACKTEST/SHADOW modes.
- **Market Data Agent** — OHLCV candles (broker history or tick aggregation),
  spread/volume, and data-quality flags (stale / high-spread) for the Risk
  Engine and pipeline.
- **Technical Analysis Agent** — multi-timeframe (1H trend + 15m setup) using
  EMA/RSI/MACD/ATR, with ATR-based stop/target and `technical/trend/volume`
  scores.
- **Decision Agent** implementing the multi-confirmation scoring/decision rules.
- **End-to-end pipeline** (`app/orchestrator.py`): Technical Analysis → Decision
  → Risk Engine → Order Manager, with portfolio state from the simulator and an
  audit trail. Executes simulated fills in SHADOW/BACKTEST; read-only otherwise.
- **Backtest engine** (`backtesting/engine.py`): replays historical 1H/15m
  candles through the pipeline, manages stop/target exits and reports metrics
  (net PnL, win rate, profit factor, max drawdown, equity curve).
- **Order Manager** safety boundary (only authorized order path; sends nothing
  to the broker in this version).
- Secure logging with secret redaction, typed models, and unit tests.

## Quick start

```bash
pip install -r requirements.txt

# Configure demo credentials (never commit .env)
cp .env.example .env
$EDITOR .env

# Read-only run: login, read account, resolve markets and prices
python -m app.main

# Run the tests
python -m pytest
```

## Operating modes

`BACKTEST`, `SHADOW`, `CAPITAL_DEMO` (default), `LIVE_DISABLED`. Live trading is
impossible to enable in this version.

## Safety model

- Only the **Order Manager** can act on orders, and only after **Risk Engine**
  approval.
- Credentials live **only** in environment variables; no secret is ever stored
  in code, config, or logs.
- Live trading cannot be enabled accidentally.

## Documentation

See [`docs/`](docs/): project spec, architecture, risk policy, CFD spec,
Capital.com integration and strategy spec.

## Project layout

```
app/  agents/  execution/  capital/  risk/  backtesting/
data/  dashboard/  monitoring/  config/  tests/  docs/
```
