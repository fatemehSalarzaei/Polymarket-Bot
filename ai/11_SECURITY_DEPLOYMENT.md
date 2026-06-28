# 11 — Security, Env and Deployment

## Forbidden in frontend
- PRIVATE_KEY
- POLYMARKET_API_SECRET
- POLYMARKET_API_PASSPHRASE
- wallet seed phrase
- signed order payloads
- direct call to `https://clob.polymarket.com/order`

## Backend env example
```env
APP_ENV=development
DATABASE_URL=postgresql+asyncpg://polymarket:polymarket@postgres:5432/polymarket_bot
REDIS_URL=redis://redis:6379/0
POLYMARKET_CLOB_HOST=https://clob.polymarket.com
POLYMARKET_GAMMA_HOST=https://gamma-api.polymarket.com
POLYMARKET_RTDS_WSS=wss://ws-live-data.polymarket.com
POLYMARKET_CHAIN_ID=137
PRIVATE_KEY=
POLYMARKET_API_KEY=
POLYMARKET_API_SECRET=
POLYMARKET_API_PASSPHRASE=
POLYMARKET_FUNDER_ADDRESS=
POLYMARKET_SIGNATURE_TYPE=3
TRADING_ENABLED=false
REDEEM_ENABLED=false
REDEEM_DRY_RUN=true
PAPER_TRADING_ENABLED=true
KILL_SWITCH_ACTIVE=false
FINAL_WINDOW_SECONDS=180
MIN_EDGE=0.04
MAX_SPREAD=0.02
MAX_SLIPPAGE=0.02
MAX_ORDER_SIZE_USD=10
MAX_DAILY_LOSS_USD=50
MAX_DATA_AGE_SECONDS=5
DEFAULT_ORDER_TYPE=FAK
```

## Frontend env example
```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api
NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws/dashboard
```

## Geoblock rule
Before real trading, call `https://polymarket.com/api/geoblock`. If blocked, force trading disabled. Do not implement bypass.

## Kill switch
- blocks all new real orders
- blocks redeem attempts
- monitoring continues
- creates audit log
- optional: cancel open orders if implemented

## Deployment
Use Docker Compose for MVP:
- postgres
- redis
- backend
- frontend

Production requirements:
- HTTPS reverse proxy
- auth for dashboard
- secrets manager
- structured logs
- database backups
- monitoring alerts
