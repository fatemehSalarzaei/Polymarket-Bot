# 02 — System Architecture

## High-level topology
```text
Frontend Dashboard
   | REST + WebSocket
Backend API / Dashboard Gateway
   |-- Market Discovery Service
   |-- Market Data Service
   |-- RTDS BTC Listener
   |-- Strategy Engine
   |-- Risk Manager
   |-- Paper Trading Engine
   |-- Execution Engine
   |-- Order Reconciler
PostgreSQL + Redis
Polymarket APIs / WebSockets
```

## Components

### Backend API
FastAPI app exposing REST and WebSocket APIs for dashboard, bot control, strategy settings, orders and PnL.

### Market Discovery Service
- compute current 15m cycle
- build slug `btc-updown-15m-{timestamp}`
- fetch event by slug
- validate active and not closed
- map `Up`/`Down` to `clobTokenIds`

### Market Data Service
- fetch initial orderbook by REST
- subscribe to CLOB market WebSocket
- normalize best bid/ask/midpoint/spread
- persist snapshots
- broadcast updates to frontend

### RTDS BTC Listener
- connect to RTDS WebSocket
- subscribe to Chainlink BTC/USD updates
- track latest BTC price and freshness

### Strategy Engine
- executes only inside final 3 minutes
- evaluates direction, edge, spread, liquidity, freshness
- returns `BUY_UP`, `BUY_DOWN`, or `NO_TRADE`

### Risk Manager
- blocks real orders when trading disabled
- blocks when geoblock blocked
- blocks stale data
- enforces max order size, max spread, max slippage, max daily loss

### Execution Engine
- backend-only CLOB SDK wrapper
- signs and submits orders only when allowed
- records raw response and errors

## Data flow
```text
cycle start -> discover market -> map tokens -> stream orderbook + BTC -> persist data
T-180s -> build strategy context -> risk check -> paper order or no trade
optional real execution -> order reconcile -> settlement/PnL
```

## Runtime note
برای realtime loops از asyncio/WebSocket استفاده شود. Celery برای این use case اصلی مناسب نیست؛ می‌تواند بعداً فقط برای گزارش‌ها یا backfill استفاده شود.
