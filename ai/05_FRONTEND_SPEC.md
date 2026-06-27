# 05 — Frontend Implementation Spec

## Structure
```text
frontend/app/
  dashboard/page.tsx
  markets/current/page.tsx
  orders/page.tsx
  strategy/page.tsx
  paper-trading/page.tsx
  pnl/page.tsx
  logs/page.tsx
  settings/page.tsx
components/{dashboard,market,strategy,orders,charts,ui}/
lib/api-client.ts
lib/websocket-client.ts
stores/dashboard-store.ts
types/{market,strategy,order,websocket}.ts
```

## Pages

### `/dashboard`
Show:
- bot status
- current market slug
- countdown
- Chainlink BTC/USD
- start price
- BTC delta
- Up/Down bid/ask
- current decision
- paper PnL
- real trading status

### `/markets/current`
Show event metadata, Up/Down orderbook table, spread, last trade, data freshness.

### `/strategy`
Editable settings:
- paperTradingEnabled
- tradingEnabled guarded
- finalWindowSeconds
- minEdge
- maxSpread
- maxSlippage
- maxOrderSizeUsd
- maxDailyLossUsd
- maxDataAgeSeconds
- orderType
- kill switch

### `/orders`
Columns:
- market
- outcome
- mode paper/real
- side
- price
- size
- status
- fill %
- reason
- submitted at

### `/pnl`
Show paper vs real summary, cumulative PnL, win rate, no-trade count.

## WebSocket events
```ts
type DashboardWsEvent =
  | { type: 'market_tick'; data: MarketTick }
  | { type: 'btc_price_tick'; data: BtcPriceTick }
  | { type: 'strategy_decision'; data: StrategyDecision }
  | { type: 'order_update'; data: OrderUpdate }
  | { type: 'bot_status'; data: BotStatus }
  | { type: 'risk_status'; data: RiskStatus }
  | { type: 'error'; data: { code: string; message: string } };
```

## UI rules
- Use Sonner for all errors.
- No full-page crash on API/WebSocket failure.
- Show stale-data badges.
- Dangerous actions require confirmation.
- Never expose secrets.
- Never call Polymarket order endpoints from frontend.
