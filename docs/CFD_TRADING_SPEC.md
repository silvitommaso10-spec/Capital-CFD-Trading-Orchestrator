# CFD Trading Specification

## Product

Contracts for Difference (CFD). A CFD position has a notional exposure but only
requires a fraction of it as margin (`margin_factor`). PnL is the price change
times size times contract size, signed by direction.

## Definitions

- **Contract size** — value of a 1.0 price-unit move, in quote currency, per
  contract. For the index/commodity/crypto CFDs modeled here it is `1.0`.
- **Notional** — `size * price * contract_size`.
- **Required margin** — `notional * margin_factor`.
- **Effective leverage** — `notional / required_margin = 1 / margin_factor`.

## PnL

For a position of `size` contracts entered at `entry_price`:

```
diff = exit_price - entry_price          # long
diff = entry_price - exit_price          # short
pnl  = diff * size * contract_size
```

## Buckets and correlation

| Bucket          | Instruments     | Notes                                   |
|-----------------|-----------------|-----------------------------------------|
| equity_indices  | US500, NASDAQ   | highly correlated → max 1 open position |
| metals          | GOLD            |                                         |
| energy          | USOIL           |                                         |
| crypto          | BTC             | higher margin requirement               |

At most **one open position per bucket** to limit correlated exposure.

## Margin factors (defaults, config/instruments.yaml)

| Symbol | margin_factor | ~leverage |
|--------|---------------|-----------|
| US500  | 0.05          | 20:1      |
| NASDAQ | 0.05          | 20:1      |
| GOLD   | 0.05          | 20:1      |
| USOIL  | 0.10          | 10:1      |
| BTC    | 0.50          | 2:1       |

These are validated against the broker's market details during the read-only
milestone and may be overridden by the live values returned by Capital.com.

## Fills (paper simulator)

The paper CFD simulator models fills with half-spread cost on entry and exit:

- Long fills at `price + spread/2`; closes at `price - spread/2`.
- Short fills at `price - spread/2`; closes at `price + spread/2`.

Margin is reserved on open and released on close; realized PnL accumulates on
the account.
