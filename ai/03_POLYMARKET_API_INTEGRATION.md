# 03 — Polymarket API Integration

## Event discovery
```http
GET https://gamma-api.polymarket.com/events/slug/{slug}
```
Slug pattern:
```text
btc-updown-15m-{start_timestamp}
```
Cycle logic:
```python
start_ts = (now_unix // 900) * 900
slug = f"btc-updown-15m-{start_ts}"
```
Always validate API response. Do not trade if event is missing, inactive, closed, or token mapping is ambiguous.

## Token mapping
Expected metadata contains outcome names and `clobTokenIds`. Map by index only after verifying arrays exist and same length.

Normalized result:
```json
{
  "event_slug": "btc-updown-15m-...",
  "condition_id": "...",
  "up_token_id": "...",
  "down_token_id": "..."
}
```

## Orderbook REST
```http
GET https://clob.polymarket.com/book?token_id={token_id}
```
Normalize:
- market
- asset_id/token_id
- timestamp
- hash
- bids
- asks
- min_order_size
- tick_size
- neg_risk
- last_trade_price
- best_bid
- best_ask
- spread

## Market WebSocket
```text
wss://clob.polymarket.com/ws/market
```
Subscription:
```json
{
  "assets_ids": ["{up_token_id}", "{down_token_id}"],
  "type": "market"
}
```
Responsibilities: reconnect, data freshness tracking, snapshot recovery after reconnect.

## RTDS BTC/USD
```text
wss://ws-live-data.polymarket.com
```
Conceptual subscription:
```json
{
  "action": "subscribe",
  "subscriptions": [
    {"topic": "crypto_prices_chainlink", "type": "update", "filters": "{\"symbol\":\"btc/usd\"}"}
  ]
}
```
If the current RTDS payload differs, update adapter but keep internal normalized schema stable.

## Auth and trading
Use official SDK where possible. Polymarket CLOB uses L1 private key signing and L2 API key/secret/passphrase for authenticated trading actions.

Required backend envs:
```env
PRIVATE_KEY=
POLYMARKET_API_KEY=
POLYMARKET_API_SECRET=
POLYMARKET_API_PASSPHRASE=
POLYMARKET_FUNDER_ADDRESS=
POLYMARKET_SIGNATURE_TYPE=3
POLYMARKET_CHAIN_ID=137
```

## Place order
```http
POST https://clob.polymarket.com/order
```
Supported order types include `GTC`, `FOK`, `GTD`, `FAK`. For final-window execution prefer `FAK` or `FOK`.

## User WebSocket
```text
wss://clob.polymarket.com/ws/user
```
Use for authenticated order/trade updates and reconciliation.

## Geoblock
```http
GET https://polymarket.com/api/geoblock
```
If blocked, force real trading off. Do not implement bypass.
