# Capital CFD Trading Orchestrator

![CI](https://github.com/silvitommaso10-spec/capital-cfd-trading-orchestrator/actions/workflows/ci.yml/badge.svg)

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
- **News Macro Agent** — maps macro events to correlation buckets, produces
  `news_score` (direction-aware), and flags contradictory unconfirmed news and
  high-impact event blackouts (→ WAIT).
- **Portfolio Agent** — equity/PnL, gross & net exposure, used margin,
  positions per bucket, and a continuous `portfolio_fit_score`.
- **Social Sentiment Agent** — a deliberately weak, bounded signal (most
  relevant for BTC) that can nudge confidence but never open a trade alone.
- **Decision Agent** implementing the multi-confirmation scoring/decision rules.
- **End-to-end pipeline** (`app/orchestrator.py`): Technical Analysis → Decision
  → Risk Engine → Order Manager, with portfolio state from the simulator and an
  audit trail. Executes simulated fills in SHADOW/BACKTEST; read-only otherwise.
- **Backtest engine** (`backtesting/engine.py`): replays historical 1H/15m
  candles through the pipeline, manages stop/target exits and reports metrics
  (net PnL, win rate, profit factor, max drawdown, equity curve).
- **Backtest CLI** (`python -m app.backtest`) with CSV loading and a `--demo`
  mode, plus a **Daily Report Agent** that summarizes pipeline runs.
- **Shadow runner** (`python -m app.shadow`) wires every agent into the
  pipeline, runs all symbols read-only, and prints the daily report.
- **Optional LLM layer** — a News interpreter (text → structured `MacroEvent`s
  feeding the deterministic News Macro Agent) and a read-only **AI Director**
  that explains decisions and suggests (never applies) tuning. Uses
  `claude-opus-4-8`; falls back to a deterministic offline mock with no API key.
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

# Run a backtest on synthetic data (no broker needed)
python -m app.backtest --demo --trade-threshold 0.5 --watchlist-threshold 0.4

# Run the full shadow pipeline across all symbols (synthetic demo)
python -m app.shadow --demo

# ...with LLM news interpretation and an AI Director briefing
# (needs ANTHROPIC_API_KEY; runs offline as a no-op without it)
python -m app.shadow --demo --news "The FOMC held rates steady." --brief

# Or from CSV candle files (timestamp,open,high,low,close,volume)
python -m app.backtest --symbol US500 \
    --candles-1h data/local/US500_1h.csv \
    --candles-15m data/local/US500_15m.csv
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
