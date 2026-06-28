from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.models import Base


async def reset_sqlite_db() -> None:
    settings = get_settings()
    if not settings.database_url.startswith("sqlite+aiosqlite"):
        raise RuntimeError("reset_sqlite_db only runs with sqlite+aiosqlite DATABASE_URL")

    engine = create_async_engine(settings.database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()


def main() -> None:
    asyncio.run(reset_sqlite_db())


if __name__ == "__main__":
    main()
