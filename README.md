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

## Local backend tests

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
pytest
```

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
- `PAPER_TRADING_ENABLED=true`
- Frontend env only contains `NEXT_PUBLIC_API_BASE_URL` and `NEXT_PUBLIC_WS_URL`
- No frontend code calls Polymarket order endpoints
- Real order execution is backend-only, guarded, and dry-run by default
