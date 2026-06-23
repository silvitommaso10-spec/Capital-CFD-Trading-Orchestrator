# Architecture

## Overview

The orchestrator is organized as a set of **analysis agents** that produce
signals/scores, a **Decision Agent** that aggregates them, a deterministic
**Risk Engine** that approves or rejects trades, and a single **Order Manager**
that is the only component permitted to act on orders.

```
            ┌──────────────┐
 data ─────▶│ Market Data  │
            └─────┬────────┘
                  ▼
   ┌───────────────────────────────────────────┐
   │ Technical | News/Macro | Sentiment | Port. │  (agents: signals only)
   └───────────────┬───────────────────────────┘
                   ▼
            ┌──────────────┐
            │ Decision     │  → trade candidate / watchlist / no trade / wait
            └─────┬────────┘
                  ▼
            ┌──────────────┐
            │ Risk Engine  │  → deterministic approve / reject
            └─────┬────────┘
                  ▼ (only if approved)
            ┌──────────────┐
            │ Order Manager│  → paper simulator (sim modes); read-only otherwise
            └──────────────┘
```

## Components

### Agents (`agents/`)
Agents are **pure analysis** — they emit a bounded `Signal` (score in `[0,1]`
plus rationale/metadata) and **cannot execute trades**.

1. **Market Data Agent** — prices, candles, spread, volume, timestamps, data quality.
   Implemented in `agents/market_data.py`: OHLCV candles from the read-only
   client or from tick aggregation (`CandleAggregator`), plus a `MarketQuality`
   assessment (stale / high-spread flags) consumed by the Risk Engine.
2. **Technical Analysis Agent** — 1H trend, 15m setups, S/R, breakouts/pullbacks, volume, RSI/MACD/EMA/ATR, stop loss and technical targets.
3. **News Macro Agent** — macro news, central banks, inflation, rates, employment, oil, geopolitics, crypto/SEC.
   Implemented in `agents/news_macro.py`: maps event categories to buckets
   (`config/news.yaml`), produces a direction-aware `news_score`, and flags
   contradictory unconfirmed news and high-impact blackouts (which drive a WAIT).
4. **Social Sentiment Agent** — social sentiment (esp. BTC). Weak signal only; cannot open a trade by itself.
   Implemented in `agents/social_sentiment.py`: aggregates weighted sentiment
   samples into a bounded score (deviation from neutral is relevance-damped per
   bucket). With a 0.05 decision weight it can only nudge confidence.
5. **Portfolio Agent** — equity, daily starting capital, PnL, open positions, exposure, margin, used risk, correlations.
   Implemented in `agents/portfolio.py`: gross/net exposure, used margin and
   utilization, positions per bucket, and a continuous `portfolio_fit_score`
   (hard 0 on a max-positions or per-bucket breach) used by the Decision Agent.
6. **Decision Agent** — aggregates the scores and produces a trade candidate, watchlist, or no-trade (or wait on news conflict).
7. **Daily Report Agent** — daily report for dashboard and email.
   Implemented in `agents/daily_report.py`: tallies pipeline results by terminal
   state and lists executed trades. Rendered to text via `app/reporting.py`; the
   backtest CLI (`python -m app.backtest`) renders the backtest report.

### Risk Engine (`risk/`)
Deterministic approve/reject for every trade. See `RISK_POLICY.md`. Includes
the **Margin Calculator** that derives position size from capital, stop
distance and the per-trade risk budget.

### Order Manager (`execution/`)
The **only** module authorized to act on orders, and only **after** Risk Engine
approval. In this version it never sends a real order: simulated modes route to
the paper simulator; `CAPITAL_DEMO`/`LIVE_DISABLED` are read-only.

### Capital.com integration (`capital/`)
Read-only client: session/auth, account, market search, symbol mapping, market
details, prices and price WebSocket. No trading endpoints are implemented; the
guard methods raise `LiveTradingDisabledError`.

### Backtesting (`backtesting/`)
Paper CFD simulator modeling fills (spread/slippage), margin and PnL, plus a
`BacktestEngine` that replays historical 1H/15m candles through the
Orchestrator. Entries come from the pipeline exactly as in shadow/live; the
engine manages stop/target exits on each new bar and reports metrics (net PnL,
return, win rate, profit factor, expectancy, max drawdown, equity curve).

### Orchestrator (`app/orchestrator.py`)
The end-to-end pipeline that ties the pieces together for one symbol:
Technical Analysis → Decision Agent → Risk Engine → Order Manager. It derives
the `PortfolioState` from the paper simulator, builds the `TradeProposal` from
the technical signal, writes a pre-trade audit record (a write failure
deterministically blocks the trade), and returns a `PipelineResult` with the
terminal state (`NO_TRADE`/`WAIT`/`WATCHLIST`/`RISK_REJECTED`/`READONLY_SKIPPED`/
`EXECUTED`). Simulated fills happen only in BACKTEST/SHADOW; CAPITAL_DEMO and
LIVE_DISABLED stop before execution.

### Optional LLM layer (`app/llm.py`, `agents/llm_news.py`, `app/ai_director.py`)
An optional, disableable layer over Claude (`claude-opus-4-8`), with a
deterministic offline mock fallback. It is used **only** to interpret text:

- **News interpreter** turns unstructured news into structured `MacroEvent`s
  that feed the deterministic News Macro Agent — the decision stays
  deterministic and auditable.
- **AI Director** is read-only: it reads the daily report and audit trail and
  produces an advisory briefing (explanations, anomalies, *suggested* tuning).

Hard boundary: LLM output never reaches the Order Manager and never overrides
the Risk Engine. The API key comes only from `ANTHROPIC_API_KEY` (environment).

## Safety invariants (enforced in code)

- Only the **Order Manager** can act on orders.
- Every trade passes through the **Risk Engine** first.
- No API key, password or token is stored in code, config, or logs.
- Credentials live **only** in environment variables.
- Live trading is **impossible to enable accidentally** (`is_live_trading_enabled`
  always returns `False`; the Order Manager refuses real orders in every mode).
- Social sentiment and news agents cannot send orders.
- Agents produce signals/scores/analysis; they never execute.

## Data flow modes

| Mode          | Data source | Fills              | Broker writes |
|---------------|-------------|--------------------|---------------|
| BACKTEST      | historical  | paper simulator    | none          |
| SHADOW        | live (RO)   | paper simulator    | none          |
| CAPITAL_DEMO  | live (RO)   | none (read-only)   | none          |
| LIVE_DISABLED | n/a         | none               | none          |
