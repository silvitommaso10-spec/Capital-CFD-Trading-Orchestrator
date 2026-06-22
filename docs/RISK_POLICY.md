# Risk Policy

The Risk Engine (`risk/engine.py`) is **deterministic**: identical inputs
always yield the identical decision, and every failed check is reported so the
audit log captures all reasons a trade was blocked.

## Limits (config/risk.yaml)

| Rule                              | Value     |
|-----------------------------------|-----------|
| Default risk per trade            | 0.75% of equity |
| Maximum risk per trade (absolute) | 1.00%     |
| Daily soft stop                   | 3%        |
| Daily hard stop                   | 5%        |
| Emergency kill switch             | 10%       |
| Max open positions                | 3         |
| Max positions per correlated bucket | 1       |
| Minimum reward/risk               | 1.8       |

## Hard requirements (a trade is rejected if violated)

- A **stop loss is mandatory** for every trade.
- **No trade on stale data** (older than `max_data_age_seconds`).
- **No trade when the spread is too high** (per-bucket/instrument threshold).
- **No trade with insufficient margin**.
- **No trade with conflicting unconfirmed news**.
- **No trade if the audit log cannot be saved**.

## Daily loss controls

`daily_pnl_fraction` is the signed PnL versus the day's starting equity.

- **Soft stop (−3%)** — risk-on exposure is reduced: the per-trade risk budget
  is halved. Trading may continue if all other checks pass.
- **Hard stop (−5%)** — no new positions are opened for the rest of the day.
- **Kill switch (−10%)** — the system halts; positions should be flattened.

## Position sizing (risk-first)

Leverage is never an objective. Given the per-trade risk budget:

```
risk_budget   = equity * risk_per_trade
stop_distance = |entry_price - stop_loss|
size          = risk_budget / (stop_distance * contract_size)
required_margin = size * entry_price * contract_size * margin_factor
```

The resulting size is snapped down to the broker's minimum deal-size
increment, then validated: the trade is rejected if `required_margin` exceeds
available margin.

## Evaluation order

1. Audit log writable
2. Stop loss present
3. Daily loss controls (kill switch / hard stop; soft stop adjusts risk)
4. Data freshness
5. Spread
6. Conflicting unconfirmed news
7. Max open positions
8. Max positions per bucket
9. Reward/risk ratio
10. Sizing + margin sufficiency

All checks are evaluated (no short-circuit) so the rejection set is complete.
