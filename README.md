# Polymarket BTC Up/Down Bot

Monitoring and paper-trading dashboard for Polymarket `btc-updown-15m-*` markets.

The implementation follows the Markdown specs in [ai/](./ai). Real trading is disabled by default and all browser-facing code talks only to the backend API.

## Run

```bash
docker compose up --build
```

Then open:

- Backend health: http://localhost:8000/api/health
- Frontend dashboard: http://localhost:3000/dashboard

Docker Compose also starts:

- `celery_worker` for scheduled market/orderbook/strategy/settlement tasks
- `celery_beat` for task scheduling
- `realtime_runner` for Polymarket market websocket and RTDS Chainlink ticks

## Local backend tests

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
pytest
```

Optional local background processes, in separate terminals:

```bash
cd backend
celery -A app.celery_app.celery_app worker --loglevel=INFO
celery -A app.celery_app.celery_app beat --loglevel=INFO
python -m app.workers.realtime_runner
```

## Manual Local Run With SQLite3

This path is for local development without PostgreSQL. Redis is still required for the Celery broker/result backend and for dashboard events published from Celery or realtime worker processes.

```bash
cp .env.sqlite.example .env
```

Install and initialize the backend:

```bash
python3 -m venv backend/.venv
source backend/.venv/bin/activate
pip install -e "backend[test]"
# or, without test tools:
# pip install -e "backend"
python -m app.scripts.init_db
```

Start Redis locally:

```bash
redis-server
```

Start the backend API:

```bash
source backend/.venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Start Celery worker and beat in separate terminals:

```bash
source backend/.venv/bin/activate
celery -A app.celery_app.celery_app worker --loglevel=INFO --pool=solo --concurrency=1
```

```bash
source backend/.venv/bin/activate
celery -A app.celery_app.celery_app beat --loglevel=INFO
```

For local SQLite, do not run multiple Celery workers against the same SQLite file. Keep worker tasks short and let each task commit promptly to reduce lock contention.

Run one redeem scan manually:

```bash
source backend/.venv/bin/activate
celery -A app.celery_app.celery_app call app.tasks.redeem.redeem_resolved_winning_positions
```

Optionally start live WebSocket ingestion:

```bash
source backend/.venv/bin/activate
python -m app.workers.realtime_runner
```

In manual SQLite mode, Celery handles scheduled polling tasks. The realtime runner is optional but recommended for live WebSocket ticks. If `realtime_runner` is not running, BTC Chainlink ticks may be missing and strategy evaluation should skip clearly with `CURRENT_CHAINLINK_TICK_MISSING`.

Start the frontend:

```bash
cd frontend
npm install
npm run dev
```

Then open:

- Backend health: http://localhost:8000/api/health
- Frontend dashboard: http://localhost:3000/dashboard

## Local frontend checks

```bash
cd frontend
npm install
npm run typecheck
npm run build
```

Playwright smoke tests are available with:

```bash
cd frontend
npx playwright install chromium
npm run test:smoke
```

## Safety defaults

- `TRADING_ENABLED=false`
- `REAL_ORDER_DRY_RUN=true`
- `REDEEM_ENABLED=false`
- `REDEEM_DRY_RUN=true`
- `PAPER_TRADING_ENABLED=true`
- Frontend env only contains `NEXT_PUBLIC_API_BASE_URL` and `NEXT_PUBLIC_WS_URL`
- No frontend code calls Polymarket order endpoints
- Real order execution is backend-only, guarded, and dry-run by default
- Redeem/claim is backend-only and dry-run by default
- The API bot start/stop endpoints record state; long-lived background work runs in Celery/realtime worker services

## Settlement, Redeem, And Wallet Balance

Settlement/PnL is internal accounting: it records which side won and calculates paper/real PnL from stored orders. It does not mean real funds have returned to the Polymarket wallet.

Redeem/claim is the separate backend-only step that can convert winning resolved real outcome tokens back into pUSD wallet balance. Losing tokens redeem for nothing, paper-only orders never call the redeem path, and `REDEEM_DRY_RUN=true` records `SKIPPED_DRY_RUN` without submitting any transaction. Redeem eligibility requires an explicit official/resolved marker in settlement metadata; market end time alone is not enough.

External withdrawal and bridging out of Polymarket are intentionally not implemented.
