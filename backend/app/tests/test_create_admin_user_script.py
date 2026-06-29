from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.user import User
from app.scripts.create_admin_user import create_or_update_admin_user, validate_role
from app.services.auth import verify_password


@pytest.fixture()
async def sessionmaker(tmp_path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    database_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield maker
    await engine.dispose()


async def _get_user(session: AsyncSession, username: str) -> User:
    result = await session.execute(select(User).where(User.username == username))
    return result.scalar_one()


@pytest.mark.asyncio
async def test_create_admin_user_defaults_to_admin(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        user = await create_or_update_admin_user(
            session,
            email="admin@example.com",
            username="admin",
            password="StrongPassword123",
            fallback_password_hash="",
            role="admin",
        )

    assert user.role == "admin"
    assert verify_password("StrongPassword123", user.password_hash)


@pytest.mark.asyncio
async def test_create_admin_user_can_create_super_user(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        user = await create_or_update_admin_user(
            session,
            email="super@example.com",
            username="superadmin",
            password="StrongPassword123",
            fallback_password_hash="",
            role="super_user",
        )

    assert user.role == "super_user"


def test_create_admin_user_rejects_invalid_role() -> None:
    with pytest.raises(SystemExit, match="Invalid role 'wsuperuser'"):
        validate_role("wsuperuser")


@pytest.mark.asyncio
async def test_existing_user_is_not_silently_overwritten(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        created = await create_or_update_admin_user(
            session,
            email="admin@example.com",
            username="admin",
            password="StrongPassword123",
            fallback_password_hash="",
            role="admin",
        )
        original_hash = created.password_hash

        existing = await create_or_update_admin_user(
            session,
            email="admin@example.com",
            username="admin",
            password="DifferentPassword123",
            fallback_password_hash="",
            role="super_user",
        )

    assert existing.role == "admin"
    assert existing.password_hash == original_hash


@pytest.mark.asyncio
async def test_existing_user_role_updates_only_with_flag(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        await create_or_update_admin_user(
            session,
            email="admin@example.com",
            username="admin",
            password="StrongPassword123",
            fallback_password_hash="",
            role="admin",
        )

        updated = await create_or_update_admin_user(
            session,
            email="admin@example.com",
            username="admin",
            password=None,
            fallback_password_hash="",
            role="super_user",
            update_role=True,
        )

    assert updated.role == "super_user"


@pytest.mark.asyncio
async def test_existing_user_password_resets_only_with_flag(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        await create_or_update_admin_user(
            session,
            email="admin@example.com",
            username="admin",
            password="StrongPassword123",
            fallback_password_hash="",
            role="admin",
        )

        updated = await create_or_update_admin_user(
            session,
            email="admin@example.com",
            username="admin",
            password="NewStrongPassword123",
            fallback_password_hash="",
            role="admin",
            reset_password=True,
        )

        stored = await _get_user(session, "admin")

    assert updated.id == stored.id
    assert verify_password("NewStrongPassword123", stored.password_hash)
