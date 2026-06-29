# Usage Guide

How to install and run the Capital CFD Trading Orchestrator.

> **First version — read-only.** This version never opens, closes, or modifies
> orders. It is for backtesting and shadow/demo *research*; nothing is sent to
> any broker. Live trading cannot be enabled.

## 1. Requirements

- Python **3.11+**
- pip
- (optional) a Capital.com **demo** account for live read-only data
- (optional) an Anthropic API key for the LLM layer

## 2. Install

```bash
git clone https://github.com/silvitommaso10-spec/capital-cfd-trading-orchestrator.git
cd capital-cfd-trading-orchestrator

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m pytest                   # optional: verify everything is green
```

`anthropic` and `websocket-client` are optional (lazily imported); the tests
and the offline demos run without them.

## 3. Try it offline (no credentials)

Everything below uses synthetic data — no broker connection required.

### Backtest with metrics

```bash
python -m app.backtest --demo --trade-threshold 0.5 --watchlist-threshold 0.4
```

Prints a report: net PnL, return %, win rate, profit factor, expectancy, max
drawdown and the trade list. Use real data with
`--candles-1h FILE --candles-15m FILE` (CSV: `timestamp,open,high,low,close,volume`).

### Backtest on real data

The `--demo` data is synthetic (a clean uptrend) — good for a sanity check, not
for real performance. For a realistic backtest you need real historical candles
as CSV. Two ways to get them:

1. **Export from Capital.com** (read-only) on a machine with network access and
   credentials configured (see §4):

   ```bash
   python -m app.fetch_candles --symbol US500 --timeframe 1H  --max 400 --out us500_1h.csv
   python -m app.fetch_candles --symbol US500 --timeframe 15m --max 400 --out us500_15m.csv

   # or export every symbol on 1H and 15m at once into data/local/
   python -m app.fetch_candles --all --out-dir data/local --max 400
   ```

2. **Bring your own CSV** from any source (header
   `timestamp,open,high,low,close,volume`; timestamps ISO 8601 or epoch).

Then backtest on it:

```bash
python -m app.backtest --symbol US500 \
    --candles-1h us500_1h.csv --candles-15m us500_15m.csv
```

### Backtest every symbol at once

If you exported with `--all` (files are named `{SYMBOL}_1H.csv` /
`{SYMBOL}_15m.csv` in one directory), run all configured instruments together
and print a side-by-side summary table:

```bash
python -m app.backtest_all --data-dir data/local
```

```
SYMBOL   TRADES  WINS   WIN%     NET PnL    RET%     PF  MAXDD%
---------------------------------------------------------------
US500         1     0   0.0%      -75.98  -0.76%   0.00   0.76%
GOLD         10     5  50.0%     +327.44  +3.27%   1.83   2.25%
USOIL         0     0   0.0%       +0.00  +0.00%   0.00   0.00%
---------------------------------------------------------------
TOTAL        11                  +251.46
```

Symbols without both CSV files are skipped and listed at the end. The same
`--trade-threshold` / `--watchlist-threshold` / `--spread` flags apply.

### Shadow run + J.A.R.V.I.S. HUD dashboard

```bash
python -m app.shadow --demo --brief --dashboard hud.html
```

Runs the full pipeline across all symbols, prints the daily report, and writes
`hud.html`. **Open `hud.html` in a browser** to see the HUD dashboard.

## 4. Live read-only mode (Capital.com demo)

Reads real demo data (account, prices, candles). Still no orders.

1. In the Capital.com platform, create an API key (**Settings → API
   integrations**) and set a custom API password.
2. Configure credentials (environment only — never in code or config):

   ```bash
   cp .env.example .env
   ```

   Fill in `.env`:

   ```dotenv
   CAPITAL_API_KEY=...          # the API key
   CAPITAL_IDENTIFIER=...       # the demo account login/email
   CAPITAL_API_PASSWORD=...     # the custom API password (not the login password)
   ```

3. Run:

   ```bash
   python -m app.main           # login + read account + read prices (read-only)
   python -m app.shadow         # pipeline on live data; simulated fills; no orders
   ```

`python -m app.main` loads config, opens a demo session, reads the account, and
prints bid/offer/spread for each mapped symbol — a quick connectivity check.

## 5. Optional: the LLM layer

Adds two optional, read-only capabilities (model `claude-opus-4-8`):

- **News interpreter** — turns free-text news into structured macro events that
  feed the deterministic News Macro Agent.
- **AI Director** — a read-only advisory briefing from the report + audit trail.

Without `ANTHROPIC_API_KEY` the system runs unchanged (deterministic fallback).
To enable, add to `.env`:

```dotenv
ANTHROPIC_API_KEY=...
```

Then:

```bash
python -m app.shadow --demo --news "The FOMC held rates steady." --brief
```

> The LLM only classifies text or advises a human. Its output never reaches the
> Order Manager and never overrides the Risk Engine.

## 6. Command reference

### `python -m app.backtest`

| Flag | Meaning |
|------|---------|
| `--demo` | Run on synthetic uptrend data |
| `--symbol US500` | Symbol to backtest |
| `--candles-1h PATH` / `--candles-15m PATH` | CSV candle files |
| `--balance 10000` | Starting balance |
| `--spread 0.2` | Assumed spread |
| `--news-score` / `--sentiment-score` | Assumed macro/sentiment backdrop |
| `--trade-threshold` / `--watchlist-threshold` | Decision thresholds |

### `python -m app.shadow`

| Flag | Meaning |
|------|---------|
| `--demo` | Synthetic data (no broker connection) |
| `--symbols US500 GOLD ...` | Symbols to run (default: all) |
| `--balance 10000` | Starting paper equity |
| `--news "..."` / `--news-file PATH` | News text for the LLM interpreter |
| `--brief` | Generate the AI Director briefing |
| `--audit-file logs/audit.jsonl` | Persist the audit trail to JSONL |
| `--dashboard out.html` | Write the HUD dashboard |

### `python -m app.main`

Read-only Capital.com demo check (login, account, prices). Requires credentials.

## 7. Configuration files (`config/`)

| File | Purpose |
|------|---------|
| `broker.yaml` | Broker endpoints, mode, credential variable names |
| `risk.yaml` | Risk limits (per-trade, daily stops, R/R, concurrency) |
| `instruments.yaml` | Symbol universe, epics, buckets, margin/spread |
| `news.yaml` | Macro categories, blackout windows, bucket impact |
| `strategy.yaml` | Per-bucket strategy profiles (EMA/ATR/R-R overrides) |

## 8. What this version does NOT do

- It does **not** place, amend, or close orders.
- It does **not** enable live trading (impossible by design in this version).

These are the next milestones (paper trading lifecycle → demo trading), built on
the deterministic Risk Engine and the single Order Manager already in place.

## 9. More documentation

See [`PROJECT_SPEC.md`](PROJECT_SPEC.md), [`ARCHITECTURE.md`](ARCHITECTURE.md),
[`RISK_POLICY.md`](RISK_POLICY.md), [`CFD_TRADING_SPEC.md`](CFD_TRADING_SPEC.md),
[`CAPITAL_COM_INTEGRATION.md`](CAPITAL_COM_INTEGRATION.md) and
[`STRATEGY_SPEC.md`](STRATEGY_SPEC.md).
