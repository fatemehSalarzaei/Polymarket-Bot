# Polymarket BTC Up/Down 15m Bot — AI/Codex Docs

این پکیج باید در ریشه پروژه داخل پوشه `ai/` قرار بگیرد و Codex باید همه مستندات را از همین مسیر بخواند. هدف نسخه اول: monitoring + dashboard + paper trading. معامله واقعی فقط بعد از تکمیل safety gates و با `TRADING_ENABLED=false` به‌صورت پیش‌فرض.

## Stack پیشنهادی
- Backend: FastAPI, Python 3.12, SQLAlchemy 2, Alembic, PostgreSQL, Redis, httpx, websockets, Pydantic v2
- Frontend: Next.js, TypeScript, Tailwind, shadcn/ui, TanStack Query, Zustand, Sonner, Recharts/lightweight-charts
- Runtime: Docker Compose
- Tests: Pytest, pytest-asyncio, Vitest, Playwright

## مسیر استفاده در پروژه

```text
project-root/
├── ai/
│   ├── README.md
│   ├── CODEX_MASTER_PROMPT.md
│   ├── 01_PROJECT_BRIEF.md
│   ├── ...
└── backend/ frontend/ ...  # توسط Codex ساخته می‌شود
```

## فایل‌ها
| File | Purpose |
|---|---|
| `01_PROJECT_BRIEF.md` | هدف، محدوده، محدودیت‌ها |
| `02_SYSTEM_ARCHITECTURE.md` | معماری کلان و data flow |
| `03_POLYMARKET_API_INTEGRATION.md` | APIهای رسمی مورد نیاز |
| `04_BACKEND_SPEC.md` | ماژول‌ها، سرویس‌ها و endpointهای backend |
| `05_FRONTEND_SPEC.md` | صفحات و کامپوننت‌های frontend |
| `06_DATABASE_SCHEMA.md` | مدل دیتابیس و migrationها |
| `07_STRATEGY_RISK.md` | strategy، risk gates، paper trading |
| `08_PHASES_TASKS.md` | فازبندی و تسک‌ها |
| `09_CODEX_PROMPTS.md` | پرامپت‌های آماده برای Codex |
| `10_TESTING_ACCEPTANCE.md` | تست‌ها و معیار پذیرش |
| `11_SECURITY_DEPLOYMENT.md` | امنیت، env و deployment |

## منابع رسمی
- https://docs.polymarket.com/api-reference/authentication
- https://docs.polymarket.com/api-reference/events/get-event-by-slug
- https://docs.polymarket.com/api-reference/market-data/get-order-book
- https://docs.polymarket.com/api-reference/wss/market
- https://docs.polymarket.com/api-reference/wss/user
- https://docs.polymarket.com/market-data/websocket/rtds
- https://docs.polymarket.com/api-reference/trade/post-a-new-order
- https://docs.polymarket.com/api-reference/geoblock
