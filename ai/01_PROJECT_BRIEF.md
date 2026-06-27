# 01 — Project Brief

## Goal
Build a monitoring and decision support system for `btc-updown-15m-*` markets in Polymarket. The first version should receive data, display a dashboard, execute the strategy in the last 3 minutes and save the result as a paper trade.

## Core flow
1. Calculate or discover the active 15-minute BTC event.
2. Receive the event with slug.
3. Extract market and token IDs of `Up` and `Down` outcomes.
4. Receive orderbook and prices.
5. Receive Chainlink BTC/USD from RTDS if available.
6. Store ticks, orderbook snapshot, strategy decision and orders.
7. Execute strategy only in `T-180s`.
8. Execute paper trade.
9. Execute real order only if all safety gates are passed.

## MVP Scope
- Current market discovery
- Live price/orderbook monitoring
- Frontend dashboard
- Strategy settings
- Paper trading
- Order/decision history
- Initial PnL summary

## Out of scope for MVP
- Profit guarantee
- Geoblock bypass
- Direct trading from frontend
- Private key storage in browser
- Multi-asset strategy
- On-chain redemption automation

## Non-negotiable rules
- `TRADING_ENABLED=false` should be the default.
- Frontend should not have any secrets or private keys.
- Order signing and order submission should be only in backend.
- If geoblock is blocked, real trading should be disabled.
- If data is stale, strategy should return `NO_TRADE`.