# 10 — Testing and Acceptance

## Backend tests
Use pytest + pytest-asyncio.

### Market discovery
- timestamp calculation
- slug builder
- active/closed validation
- Up/Down token mapping
- ambiguous mapping failure

### Orderbook
- best bid/highest bid
- best ask/lowest ask
- midpoint
- spread
- empty book handling
- stale detection

### RTDS
- valid BTC tick parsing
- stale data
- reconnect behavior

### Strategy
- no run before final window
- BUY_UP when edge passes
- BUY_DOWN when edge passes
- NO_TRADE when edge low
- NO_TRADE when spread high
- NO_TRADE when data stale

### Risk manager
- kill switch blocks real order
- trading disabled blocks real order
- geoblock blocks real order
- max order size blocks order
- daily loss blocks order

### Execution
- dry-run does not submit
- disabled trading does not submit
- mocked SDK submit succeeds/fails and persists result

## Frontend tests
- dashboard loading state
- data state
- settings validation
- orders empty state
- API failure toast
- WebSocket reconnect behavior

## Playwright smoke
- `/dashboard`
- `/markets/current`
- `/strategy`
- edit setting
- `/orders`
- `/pnl`

## Acceptance checklist
- Docker Compose starts
- Health endpoint works
- Current market discovery works
- Orderbook ingestion works
- BTC RTDS freshness works
- Dashboard updates live
- Strategy persists all decisions
- Paper orders created
- Real trading disabled by default
- Geoblock check exists
- Kill switch exists
- No secrets in frontend
