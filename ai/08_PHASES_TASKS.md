# 08 — Phases and Tasks

## Phase 0 — Scaffold
- Create monorepo: backend, frontend, docker-compose
- FastAPI health endpoint
- Next.js dashboard placeholder
- Postgres + Redis
- `.env.example`
- `TRADING_ENABLED=false`

## Phase 1 — Market discovery
- Implement cycle timestamp
- Build `btc-updown-15m-{ts}` slug
- Fetch event by slug
- Parse event/market
- Map Up/Down token IDs safely
- Persist market
- Expose `GET /api/markets/current`

## Phase 2 — Data ingestion
- Fetch orderbook REST
- Normalize bid/ask/spread
- Store snapshots
- Connect market WebSocket
- Connect RTDS BTC/USD
- Track freshness
- Broadcast to frontend WebSocket

## Phase 3 — Backend APIs
- Bot status
- Current market
- Current orderbook
- BTC price
- Strategy settings GET/PATCH
- Orders endpoint
- Decisions endpoint
- Audit logging

## Phase 4 — Frontend dashboard
- Layout/sidebar
- Dashboard cards
- Current market page
- WebSocket client
- Zustand store
- Settings form
- Sonner error handling

## Phase 5 — Strategy + paper trading
- Strategy context builder
- Final-window scheduler
- Strategy decision logic
- Risk manager
- Persist decisions
- Create paper orders
- Decision/order UI

## Phase 6 — Guarded real execution
- Backend SDK wrapper
- Geoblock check
- Execution engine
- User WebSocket listener
- Reconciliation
- Kill switch
- Dry-run mode

## Phase 7 — Reports and hardening
- Settlement worker
- PnL summary
- PnL frontend page
- Logs page
- Structured logs
- Playwright smoke tests
- CI if applicable

## Mandatory order
```text
P0 -> P1 -> P2 -> P3 -> P4 -> P5 -> P6 -> P7
```
Never implement P6 before P0-P5 pass tests.
