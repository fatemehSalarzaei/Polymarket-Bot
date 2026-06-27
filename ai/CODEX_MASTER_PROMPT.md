# Codex Master Prompt

```text
Read every Markdown file under the ./ai directory before coding. Treat ./ai as the single source of truth for product scope, architecture, phases, APIs, tests, and safety constraints.

Implement this project phase by phase using only the specifications inside ./ai:
P0 scaffold, P1 market discovery, P2 data ingestion, P3 backend APIs, P4 frontend dashboard, P5 strategy + paper trading, P6 guarded real execution, P7 reports/hardening.

Repository layout rule:
- Keep all planning/specification documents inside ./ai.
- Do not move implementation source code into ./ai. Backend, frontend, infra, tests, and runtime files must be created outside ./ai.

Rules:
- Never expose secrets in frontend.
- Never submit Polymarket orders from frontend.
- Keep TRADING_ENABLED=false by default.
- Implement geoblock check and do not bypass it.
- Use backend-only signing/execution.
- Add tests for core logic.
- Use official Polymarket APIs/SDKs where practical.
- Do not claim guaranteed profit.
```
