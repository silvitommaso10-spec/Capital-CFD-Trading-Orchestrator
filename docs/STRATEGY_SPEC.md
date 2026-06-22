# Strategy Specification

## Initial strategy: multi-confirmation

- **1H** defines the main trend.
- **15m** defines the entry timing.
- **Volume** confirms breakouts/breakdowns.
- **News & macro** filter or block a trade.
- **Social sentiment** can only slightly increase or decrease confidence.
- The **Risk Engine** decides whether the trade is allowed.

## Scoring formula

```
final_score = technical_score   * 0.40
            + trend_score        * 0.20
            + volume_score       * 0.15
            + news_score         * 0.15
            + sentiment_score    * 0.05
            + portfolio_fit_score* 0.05
```

All component scores are in `[0, 1]` (clamped). The weights sum to `1.0`.
Implemented in `agents/decision_agent.py`.

## Decision rules

| Condition                         | Outcome          |
|-----------------------------------|------------------|
| `final_score >= 0.72`             | TRADE_CANDIDATE  |
| `0.60 <= final_score < 0.72`      | WATCHLIST        |
| `final_score < 0.60`              | NO_TRADE         |
| News conflict                     | WAIT             |
| Risk rejection                    | NO_TRADE         |

Hard gates (news conflict, risk rejection) take precedence over the numeric
score. A `TRADE_CANDIDATE` is only a proposal — it must still be approved by
the Risk Engine before the Order Manager can act on it.

## Sentiment constraint

The sentiment weight is `0.05`, so sentiment can only nudge the final score
within a small band. It can never, on its own, push a trade across the
`TRADE_CANDIDATE` threshold or open a position — consistent with the rule that
the Social Sentiment Agent produces a weak signal only.

## Technical Analysis Agent (implemented)

`agents/technical_analysis.py` produces the technical/trend/volume scores from
1H and 15m candles:

- **Trend (1H)** — EMA(20) vs EMA(50) alignment plus a minimum-strength gate
  (separation normalized by ATR). Yields `UP`/`DOWN`/`SIDEWAYS` and a
  `trend_score`. A directional trend is required to propose a trade.
- **Setup (15m)** — combines EMA(9/21) alignment, price vs fast EMA, MACD
  histogram and RSI (with overbought/oversold fading) into `technical_score`.
- **Volume** — last bar volume vs its 20-bar average → `volume_score`.
- **Stop/target** — ATR-based: stop at `1.5 × ATR`, target at `reward_risk ×`
  the stop distance (default 2.0), giving an R/R that clears the risk policy's
  1.8 minimum.

Indicator primitives (SMA, EMA, RSI, MACD, ATR) live in `agents/indicators.py`.

## Notes for later milestones

- The Market Data Agent will build the 1H/15m candles and data-quality flags
  that feed the Technical Analysis Agent.
- News score will incorporate the macro blackout windows from `config/news.yaml`.
- Portfolio-fit score will reflect correlation/bucket exposure and used risk.
