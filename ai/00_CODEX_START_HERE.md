# 00 — Codex Start Here

This `ai/` folder is the main source of project documentation. Codex should read these files before any code changes and run the project based only on this documentation.

## Reading order

1. `README.md`
2. `CODEX_MASTER_PROMPT.md`
3. `01_PROJECT_BRIEF.md`
4. `02_SYSTEM_ARCHITECTURE.md`
5. `03_POLYMARKET_API_INTEGRATION.md`
6. `04_BACKEND_SPEC.md`
7. `05_FRONTEND_SPEC.md`
8. `06_DATABASE_SCHEMA.md`
9. `07_STRATEGY_RISK.md`
10. `08_PHASES_TASKS.md`
11. `09_CODEX_PROMPTS.md`
12. `10_TESTING_ACCEPTANCE.md`
13. `11_SECURITY_DEPLOYMENT.md`

## Project structure rule

Executable code, backend, frontend, infra, test and runtime files should not be built into `ai/`. This folder is only for documentation, architectural decisions, phases, and Codex execution prompts.

## Start execution

First, give Codex the text in `CODEX_MASTER_PROMPT.md`. Then execute the step-by-step prompts in `09_CODEX_PROMPTS.md` in order.