from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.models.market import Market
from app.models.user import User
from app.models.wallet import WalletCredential
from app.services.auth import AUTH_COOKIE_NAME, create_access_token, hash_password


@pytest.fixture()
async def sessionmaker(tmp_path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    database_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield maker
    await engine.dispose()


@pytest.fixture()
def client(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncIterator[TestClient]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _seed_user(sessionmaker: async_sessionmaker[AsyncSession], *, role: str) -> User:
    async def seed() -> User:
        async with sessionmaker() as session:
            user = User(
                username=f"{role}_user",
                email=f"{role}@example.com",
                password_hash=hash_password("password1234"),
                role=role,
                is_active=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    return asyncio.run(seed())


def _authenticate(client: TestClient, user: User) -> None:
    client.cookies.set(AUTH_COOKIE_NAME, create_access_token(user))


def test_admin_panel_allows_super_user_login(client: TestClient, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    _seed_user(sessionmaker, role="super_user")

    response = client.post(
        "/admin-panel/login",
        data={"username": "super_user_user", "password": "password1234"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin-panel"
    assert AUTH_COOKIE_NAME in response.headers["set-cookie"]


def test_admin_user_form_uses_role_select(client: TestClient, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    user = _seed_user(sessionmaker, role="super_user")
    _authenticate(client, user)

    response = client.get("/admin-panel/tables/users/new")

    assert response.status_code == 200
    assert '<select id="role" name="role"' in response.text
    assert 'value="super_user"' in response.text
    assert 'value="admin"' in response.text


def test_admin_panel_rejects_arbitrary_role(client: TestClient, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    user = _seed_user(sessionmaker, role="super_user")
    _authenticate(client, user)

    response = client.post(
        "/admin-panel/tables/users/new",
        data={
            "username": "badrole",
            "email": "badrole@example.com",
            "password": "password1234",
            "role": "owner",
            "is_active": "on",
        },
    )

    assert response.status_code == 200
    assert "Role must be one of the allowed values." in response.text


def test_non_super_user_cannot_create_admin_panel_record(
    client: TestClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    user = _seed_user(sessionmaker, role="admin")
    _authenticate(client, user)

    response = client.get("/admin-panel/tables/users/new")

    assert response.status_code == 403
    assert "does not allow creating records" in response.text


def test_market_list_uses_compact_columns(client: TestClient, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    user = _seed_user(sessionmaker, role="admin")

    async def seed_market() -> None:
        async with sessionmaker() as session:
            session.add(
                Market(
                    event_slug="btc-updown",
                    market_slug="btc-updown-15m",
                    condition_id="condition-1",
                    question="BTC Up or Down?",
                    active=True,
                    closed=False,
                    up_token_id="up",
                    down_token_id="down",
                    raw_event={"large": "payload"},
                    raw_market={"large": "payload"},
                )
            )
            await session.commit()

    asyncio.run(seed_market())
    _authenticate(client, user)

    response = client.get("/admin-panel/tables/markets")

    assert response.status_code == 200
    assert "Event Slug" in response.text
    assert "Raw Event" not in response.text
    assert "Raw Market" not in response.text


def test_wallet_credentials_masked_never_show_secret_fields(
    client: TestClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    user = _seed_user(sessionmaker, role="admin")

    async def seed_wallet() -> None:
        async with sessionmaker() as session:
            session.add(
                WalletCredential(
                    user_id=user.id,
                    wallet_address="0x1234567890abcdef",
                    encrypted_private_key="private-secret",
                    encrypted_api_key="api-key-secret",
                    encrypted_api_secret="api-secret",
                    encrypted_api_passphrase="api-passphrase",
                    is_configured=True,
                    is_active=True,
                )
            )
            await session.commit()

    asyncio.run(seed_wallet())
    _authenticate(client, user)

    response = client.get("/admin-panel/tables/wallet_credentials_masked")

    assert response.status_code == 200
    assert "0x1234...cdef" in response.text
    assert "private-secret" not in response.text
    assert "api-key-secret" not in response.text
    assert "api-secret" not in response.text


def test_api_admin_user_mutation_requires_super_user(
    client: TestClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    user = _seed_user(sessionmaker, role="admin")
    _authenticate(client, user)

    response = client.post(
        "/api/admin/users",
        json={
            "username": "created",
            "email": "created@example.com",
            "password": "password1234",
            "role": "viewer",
            "is_active": True,
        },
    )

    assert response.status_code == 403


def test_api_admin_roles_returns_safe_options(client: TestClient, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    user = _seed_user(sessionmaker, role="admin")
    _authenticate(client, user)

    response = client.get("/api/admin/roles")

    assert response.status_code == 200
    assert {"value": "super_user", "label": "Super User"} in response.json()["roles"]


def test_created_user_password_is_hashed(client: TestClient, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    user = _seed_user(sessionmaker, role="super_user")
    _authenticate(client, user)

    response = client.post(
        "/admin-panel/tables/users/new",
        data={
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "password1234",
            "role": "viewer",
            "is_active": "on",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303

    async def get_created() -> User:
        async with sessionmaker() as session:
            result = await session.execute(select(User).where(User.username == "newuser"))
            return result.scalar_one()

    created = asyncio.run(get_created())
    assert created.password_hash.startswith("pbkdf2_sha256$")
    assert created.password_hash != "password1234"
