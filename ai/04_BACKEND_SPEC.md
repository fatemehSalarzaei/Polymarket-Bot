# 04 — Backend Implementation Spec

## Structure
```text
backend/app/
  main.py
  core/config.py
  core/logging.py
  db/session.py
  models/{market,tick,strategy,order,settings,audit}.py
  schemas/{market,strategy,order,settings,websocket}.py
  services/
    polymarket_gamma.py
    polymarket_clob.py
    market_discovery.py
    market_ws.py
    rtds_ws.py
    strategy_engine.py
    risk_manager.py
    paper_trading.py
    execution_engine.py
    order_reconciler.py
    dashboard_broadcaster.py
  api/routes/{health,markets,bot,strategy,orders,pnl,settings,ws}.py
  tests/
```

## Services

### PolymarketGammaClient
```python
async def get_event_by_slug(slug: str) -> PolymarketEventDTO: ...
```

### PolymarketClobClient
```python
async def get_orderbook(token_id: str) -> OrderBookDTO: ...
async def place_order(request: PlaceOrderRequest) -> PlaceOrderResult: ...
async def get_order(order_id: str) -> OrderDTO: ...
async def cancel_order(order_id: str) -> CancelOrderResult: ...
```

### MarketDiscoveryService
```python
def compute_cycle_start(now: datetime) -> int: ...
def build_btc_15m_slug(start_ts: int) -> str: ...
async def discover_current_market() -> ActiveMarketDTO: ...
```

### StrategyEngine
```python
async def evaluate(context: StrategyContext) -> StrategyDecision: ...
```
Must not submit orders directly.

### RiskManager
```python
async def validate_for_paper_trade(decision: StrategyDecision) -> RiskResult: ...
async def validate_for_real_trade(decision: StrategyDecision) -> RiskResult: ...
```

### ExecutionEngine
```python
async def submit_real_order(decision: StrategyDecision) -> RealOrderResult: ...
```
Must block unless `TRADING_ENABLED=true` and all gates pass.

## REST endpoints
```http
GET /api/health
GET /api/markets/current
GET /api/markets/current/orderbook
GET /api/markets/current/btc
GET /api/bot/status
POST /api/bot/start
POST /api/bot/stop
POST /api/bot/kill-switch
GET /api/strategy/settings
PATCH /api/strategy/settings
GET /api/strategy/current-decision
GET /api/strategy/decisions
GET /api/orders
GET /api/pnl/summary
WS /ws/dashboard
```

## Logging
Use structured JSON logs. Redact secrets. Log every strategy decision with inputs, edge, risk result, and final decision.
