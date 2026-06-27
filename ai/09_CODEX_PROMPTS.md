# 09 — Codex Execution Prompts

## Global instruction
```text
You are implementing this repository from the Markdown specs under ./ai. Work phase by phase. Do not expose secrets in frontend. Do not call Polymarket order endpoints from frontend. Keep TRADING_ENABLED=false by default. Do not implement geoblock bypass. Add tests for core logic.
```

## Prompt 1 — Scaffold
```text
Read ai/README.md, ai/01_PROJECT_BRIEF.md, ai/02_SYSTEM_ARCHITECTURE.md, ai/08_PHASES_TASKS.md. Implement Phase 0 only: monorepo, FastAPI health, Next.js dashboard placeholder, Docker Compose with Postgres/Redis, env examples, safety defaults. Acceptance: docker compose up works, /api/health returns ok, /dashboard renders, no secrets committed.
```

## Prompt 2 — DB and settings
```text
Read ai/04_BACKEND_SPEC.md and ai/06_DATABASE_SCHEMA.md. Implement SQLAlchemy models, Alembic migrations, DB session, strategy_settings default row, audit_logs, GET/PATCH /api/strategy/settings. Acceptance: migrations run, default settings exist, PATCH validates values and writes audit logs.
```

## Prompt 3 — Market discovery
```text
Read ai/03_POLYMARKET_API_INTEGRATION.md and ai/04_BACKEND_SPEC.md. Implement PolymarketGammaClient, MarketDiscoveryService, cycle timestamp, slug builder, event parser, Up/Down token mapper, markets persistence, GET /api/markets/current. Add unit tests for boundary timestamps and ambiguous token mapping.
```

## Prompt 4 — Orderbook REST
```text
Implement PolymarketClobClient.get_orderbook, DTOs, best bid/ask/midpoint/spread, orderbook_snapshots persistence, GET /api/markets/current/orderbook. Mock Polymarket response in tests.
```

## Prompt 5 — WebSockets
```text
Implement MarketWebSocketService, RTDSWebSocketService, DashboardBroadcaster, WS /ws/dashboard, reconnect with backoff, freshness tracking. Use mock websocket messages in tests.
```

## Prompt 6 — Frontend dashboard
```text
Read ai/05_FRONTEND_SPEC.md. Implement typed API client, websocket client, Zustand store, /dashboard, /markets/current, dashboard cards, data freshness badges, Sonner error handling. Acceptance: REST initial load, WebSocket updates, no page crash on failure.
```

## Prompt 7 — Strategy and paper trading
```text
Read ai/07_STRATEGY_RISK.md. Implement StrategyContext, StrategyEngine, RiskManager, PaperTradingEngine, strategy_decisions persistence, paper orders persistence, current decision endpoint, decision history endpoint, orders endpoint. Tests must cover final-window, edge too low, spread too high, stale data, and paper order creation.
```

## Prompt 8 — Strategy/orders UI
```text
Implement /strategy and /orders pages. Add settings form, decision card, decision history, orders table, confirmation modal for dangerous settings, kill switch UI. Errors must use Sonner.
```

## Prompt 9 — Guarded real execution
```text
Implement backend-only SDK wrapper, geoblock check, ExecutionEngine, UserWebSocket listener, reconciliation, dry-run mode, POST /api/bot/kill-switch, GET /api/bot/geoblock-status. Keep real trading disabled by default. Mock all real order tests.
```

## Prompt 10 — Reports and hardening
```text
Implement settlement worker, PnL summary endpoint, /pnl page, logs page, structured logging, Playwright smoke tests. Verify backend tests, frontend typecheck, and docker compose startup.
```

## Prompt 11 — Final review
```text
Review repository against all Markdown specs under ./ai. Verify no frontend secrets, no direct frontend order calls, TRADING_ENABLED=false default, geoblock check, kill switch, tests, Docker Compose and README run instructions. Fix mismatches only.
```
