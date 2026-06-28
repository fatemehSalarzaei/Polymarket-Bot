from __future__ import annotations

import importlib
import os
import subprocess
import sys

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.scripts.init_db import init_db
from app.scripts.reset_sqlite_db import reset_sqlite_db


@pytest.fixture(autouse=True)
def clear_settings_caches():
    get_settings.cache_clear()
    get_sessionmaker.cache_clear()
    yield
    get_settings.cache_clear()
    get_sessionmaker.cache_clear()


@pytest.mark.asyncio
async def test_settings_can_load_sqlite_database_url(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path}/settings.db"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()

    assert get_settings().database_url == database_url


@pytest.mark.asyncio
async def test_init_db_creates_all_tables_in_sqlite(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path}/init.db"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()

    await init_db()

    engine = create_async_engine(database_url)
    async with engine.connect() as connection:
        table_names = await connection.run_sync(lambda sync_connection: inspect(sync_connection).get_table_names())
    await engine.dispose()

    assert {"markets", "orders", "strategy_decisions", "chainlink_ticks"}.issubset(set(table_names))


@pytest.mark.asyncio
async def test_reset_sqlite_db_refuses_non_sqlite_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/db")
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="only runs with sqlite"):
        await reset_sqlite_db()


def test_celery_app_imports_with_sqlite_env(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path}/celery.db"
    env = {**os.environ, "DATABASE_URL": database_url, "REDIS_URL": "redis://localhost:6379/0"}

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.celery_app import celery_app; print(celery_app.main)",
        ],
        cwd=os.getcwd(),
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert result.stdout.strip() == "polymarket_bot"


def test_evaluate_current_strategy_task_runs_after_sqlite_init(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path}/strategy-task.db"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    get_sessionmaker.cache_clear()

    importlib.reload(importlib.import_module("app.celery_app"))
    strategy_tasks = importlib.reload(importlib.import_module("app.tasks.strategy_tasks"))

    import asyncio

    asyncio.run(init_db())
    result = strategy_tasks.evaluate_current_strategy_task()

    assert result["decision_id"] is None
    assert "CURRENT_MARKET_MISSING" in result["missing"]

    get_sessionmaker.cache_clear()
