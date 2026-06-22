# Capital.com Integration (Read-Only)

This milestone integrates with the **Capital.com demo** REST and streaming API
in a strictly **read-only** manner.

## Credentials

Credentials come **only** from environment variables — never from code, config,
or logs. Copy `.env.example` to `.env` and fill in:

| Variable                | Meaning                                            |
|-------------------------|----------------------------------------------------|
| `CAPITAL_API_KEY`       | API key created in the Capital.com platform        |
| `CAPITAL_IDENTIFIER`    | Account identifier (login/email)                   |
| `CAPITAL_API_PASSWORD`  | The custom API password (not the login password)   |

`app/env.py` loads and validates these; the `Credentials` dataclass overrides
`__repr__` so secrets never appear in tracebacks or logs. The secure logging
filter (`app/logging_utils.py`) additionally redacts any leaked secret-like
key/value pairs (api keys, `CST`, `X-SECURITY-TOKEN`, passwords, tokens).

## Endpoints (demo)

- REST base: `https://demo-api-capital.backend-capital.com`
- WebSocket: `wss://api-streaming-capital.backend-capital.com/connect`

Configured in `config/broker.yaml`.

## Session / authentication

`POST /api/v1/session` with header `X-CAP-API-KEY` and a JSON body of
`{identifier, password}`. The response headers `CST` and `X-SECURITY-TOKEN` are
captured into a `CapitalSession` and sent on subsequent read requests. Sessions
are refreshed proactively before expiry.

## Read-only operations implemented

| Operation        | Endpoint                                  | Returns          |
|------------------|-------------------------------------------|------------------|
| Account read     | `GET /api/v1/accounts`                    | `Account[]`      |
| Market search    | `GET /api/v1/markets?searchTerm=...`      | `MarketSummary[]`|
| Market details   | `GET /api/v1/markets/{epic}`              | `MarketDetails`  |
| Latest price     | `GET /api/v1/markets/{epic}` (snapshot)   | `Price`          |
| Historical prices| `GET /api/v1/prices/{epic}`               | `Price[]`        |
| Price stream     | WebSocket `marketData.subscribe`          | callback         |

## Symbol mapping

`config/instruments.yaml` seeds the logical-symbol → epic mapping
(`capital/mapper.py`). Resolved epics are validated against market search and
can be re-registered with the broker's actual epic.

| Symbol | Default epic |
|--------|--------------|
| US500  | `US500`      |
| NASDAQ | `US100`      |
| GOLD   | `GOLD`       |
| USOIL  | `OIL_CRUDE`  |
| BTC    | `BTCUSD`     |

> The default epics are best-effort and confirmed at runtime via market search,
> since Capital.com epics can differ per account.

## No trading

`CapitalClient` exposes no method to open, amend, or close positions/orders.
The guard methods `place_order`, `create_position`, `update_position` and
`close_position` exist only to raise `LiveTradingDisabledError` if called.

## Error handling & resilience

The transport retries transient failures (network errors and HTTP
429/500/502/503/504) with exponential backoff. Authentication failures raise
`AuthenticationError`; expired sessions raise `SessionExpiredError` and trigger
a re-login; unknown markets raise `MarketNotFoundError`.

## Running the read-only check

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in your demo credentials
python -m app.main
```
