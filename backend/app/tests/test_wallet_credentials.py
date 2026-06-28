from collections.abc import AsyncIterator
import logging
import sys
from types import ModuleType

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.routes.wallet import get_api_credential_deriver
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.models.wallet import WalletCredential
from app.schemas.wallet import WalletConfigureRequest
from app.services.secret_crypto import decrypt_secret
from app.services.wallet_credentials import (
    PolymarketSdkCredentialDeriver,
    configure_wallet,
    derive_wallet_address,
    get_active_wallet_credentials_for_trading,
    normalize_polymarket_api_creds,
    validate_private_key,
)

PRIVATE_KEY = "0x0000000000000000000000000000000000000000000000000000000000000001"


class FakeCredentialDeriver:
    def __init__(self, suffix: str = "one") -> None:
        self.suffix = suffix

    async def create_or_derive_api_credentials(self, **kwargs):
        return {
            "api_key": f"api-key-{self.suffix}",
            "api_secret": f"api-secret-{self.suffix}",
            "api_passphrase": f"api-passphrase-{self.suffix}",
        }


class RaisingCredentialDeriver:
    async def create_or_derive_api_credentials(self, **kwargs):
        raise AssertionError("Polymarket should not be called")


class ApiCredsLike:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_secret: str | None = None,
        api_passphrase: str | None = None,
        apiKey: str | None = None,
        key: str | None = None,
        secret: str | None = None,
        passphrase: str | None = None,
    ) -> None:
        if api_key is not None:
            self.api_key = api_key
        if api_secret is not None:
            self.api_secret = api_secret
        if api_passphrase is not None:
            self.api_passphrase = api_passphrase
        if apiKey is not None:
            self.apiKey = apiKey
        if key is not None:
            self.key = key
        if secret is not None:
            self.secret = secret
        if passphrase is not None:
            self.passphrase = passphrase


@pytest.fixture(autouse=True)
def encryption_key(monkeypatch) -> AsyncIterator[None]:
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
async def sessionmaker(tmp_path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    database_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield maker
    await engine.dispose()


def test_private_key_validation_rejects_invalid_keys() -> None:
    with pytest.raises(AppError) as exc:
        validate_private_key("not-a-key")

    assert exc.value.code == "WALLET_PRIVATE_KEY_INVALID"


@pytest.mark.asyncio
async def test_invalid_private_key_is_rejected_before_polymarket_call(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        with pytest.raises(AppError) as exc:
            await configure_wallet(
                WalletConfigureRequest(private_key="0xnot-valid", derive_api_credentials=True),
                session,
                deriver=RaisingCredentialDeriver(),
            )

    assert exc.value.code == "WALLET_PRIVATE_KEY_INVALID"


def test_wallet_address_is_derived_from_private_key() -> None:
    assert derive_wallet_address(PRIVATE_KEY) == "0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf"


def test_normalize_dict_with_api_key_secret_passphrase() -> None:
    assert normalize_polymarket_api_creds(
        {"apiKey": "api-key", "secret": "secret", "passphrase": "passphrase"}
    ) == {
        "api_key": "api-key",
        "api_secret": "secret",
        "api_passphrase": "passphrase",
    }


def test_normalize_dict_with_key_secret_passphrase() -> None:
    assert normalize_polymarket_api_creds(
        {"key": "api-key", "secret": "secret", "passphrase": "passphrase"}
    ) == {
        "api_key": "api-key",
        "api_secret": "secret",
        "api_passphrase": "passphrase",
    }


def test_normalize_api_creds_like_object() -> None:
    creds = ApiCredsLike(api_key="api-key", api_secret="secret", api_passphrase="passphrase")

    assert normalize_polymarket_api_creds(creds) == {
        "api_key": "api-key",
        "api_secret": "secret",
        "api_passphrase": "passphrase",
    }


def test_invalid_credential_response_omits_secret_values() -> None:
    with pytest.raises(AppError) as exc:
        normalize_polymarket_api_creds(ApiCredsLike(api_key="api-key", api_secret="very-secret"))

    assert exc.value.code == "WALLET_API_CREDENTIAL_RESPONSE_INVALID"
    detail = exc.value.technical_detail or ""
    assert "ApiCredsLike" in detail
    assert "api_secret" in detail
    assert "very-secret" not in detail


@pytest.mark.asyncio
async def test_configure_encrypts_secrets_and_status_is_safe(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        credential = await configure_wallet(
            WalletConfigureRequest(private_key=PRIVATE_KEY),
            session,
            deriver=FakeCredentialDeriver(),
        )

    async with sessionmaker() as session:
        row = (await session.execute(select(WalletCredential).where(WalletCredential.id == credential.id))).scalar_one()
        assert PRIVATE_KEY not in row.encrypted_private_key
        assert "api-secret-one" not in (row.encrypted_api_secret or "")
        assert decrypt_secret(row.encrypted_private_key) == PRIVATE_KEY

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        with TestClient(app) as client:
            response = client.get("/api/wallet")
    finally:
        app.dependency_overrides.clear()

    body = response.json()
    assert response.status_code == 200
    assert body["configured"] is True
    assert body["api_key_configured"] is True
    assert body["api_key_masked"] == "api-ke...-one"
    assert "private_key" not in body
    assert "api_secret" not in body
    assert "api_passphrase" not in body


def test_configure_endpoint_uses_singleton_wallet_record(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_api_credential_deriver] = lambda: FakeCredentialDeriver()
    try:
        with TestClient(app) as client:
            first = client.post("/api/wallet/configure", json={"private_key": PRIVATE_KEY})
            second = client.post(
                "/api/wallet/configure",
                json={
                    "private_key": "0x0000000000000000000000000000000000000000000000000000000000000002",
                    "derive_api_credentials": False,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert second.status_code == 200

    import asyncio

    async def assert_singleton() -> None:
        async with sessionmaker() as session:
            rows = (await session.execute(select(WalletCredential))).scalars().all()
            assert len(rows) == 1
            assert rows[0].wallet_address == "0x2B5AD5c4795c026514f8317c7a215E218DcCD6cF"

    asyncio.run(assert_singleton())


@pytest.mark.asyncio
async def test_derive_api_credentials_updates_encrypted_credentials(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        await configure_wallet(
            WalletConfigureRequest(private_key=PRIVATE_KEY, derive_api_credentials=False),
            session,
            deriver=FakeCredentialDeriver("old"),
        )
        credential = await get_active_wallet_credentials_for_trading_or_none(session)
        assert credential is None

    from app.services.wallet_credentials import derive_api_credentials

    async with sessionmaker() as session:
        updated = await derive_api_credentials(session, deriver=FakeCredentialDeriver("new"))
        assert decrypt_secret(updated.encrypted_api_key or "") == "api-key-new"


@pytest.mark.asyncio
async def test_sdk_response_with_api_key_is_supported(monkeypatch) -> None:
    fake_client = _install_fake_clob_client(monkeypatch, {"apiKey": "api-key", "secret": "secret", "passphrase": "pass"})

    payload = await PolymarketSdkCredentialDeriver().create_or_derive_api_credentials(
        private_key=PRIVATE_KEY,
        chain_id=137,
        funder_address="0xfunder",
        signature_type=3,
    )

    assert payload == {"api_key": "api-key", "api_secret": "secret", "api_passphrase": "pass"}
    assert fake_client.last_kwargs == {"host": "https://clob.polymarket.com", "chain_id": 137, "key": PRIVATE_KEY}


@pytest.mark.asyncio
async def test_sdk_response_with_key_is_supported(monkeypatch) -> None:
    _install_fake_clob_client(monkeypatch, {"key": "api-key", "secret": "secret", "passphrase": "pass"})

    payload = await PolymarketSdkCredentialDeriver().create_or_derive_api_credentials(
        private_key=PRIVATE_KEY,
        chain_id=137,
        funder_address=None,
        signature_type=0,
    )

    assert payload["api_key"] == "api-key"


@pytest.mark.asyncio
async def test_create_or_derive_returning_api_creds_object_is_supported(monkeypatch, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    _install_fake_clob_client(
        monkeypatch,
        ApiCredsLike(api_key="api-key-object", api_secret="secret-object", api_passphrase="pass-object"),
    )

    async with sessionmaker() as session:
        credential = await configure_wallet(WalletConfigureRequest(private_key=PRIVATE_KEY), session)

    assert decrypt_secret(credential.encrypted_api_key or "") == "api-key-object"
    assert decrypt_secret(credential.encrypted_api_secret or "") == "secret-object"
    assert decrypt_secret(credential.encrypted_api_passphrase or "") == "pass-object"


@pytest.mark.asyncio
async def test_missing_secret_or_passphrase_returns_invalid_response(monkeypatch) -> None:
    _install_fake_clob_client(monkeypatch, {"apiKey": "api-key", "secret": "super-secret"})

    with pytest.raises(AppError) as exc:
        await PolymarketSdkCredentialDeriver().create_or_derive_api_credentials(
            private_key=PRIVATE_KEY,
            chain_id=137,
            funder_address=None,
            signature_type=3,
        )

    assert exc.value.code == "WALLET_API_CREDENTIAL_RESPONSE_INVALID"
    assert "apiKey" in (exc.value.technical_detail or "")
    assert "super-secret" not in (exc.value.technical_detail or "")


@pytest.mark.asyncio
async def test_polymarket_400_without_creds_maps_to_derivation_failed(monkeypatch) -> None:
    _install_fake_clob_client(monkeypatch, RuntimeError('status=400 body={"error":"Could not create api key"}'))

    with pytest.raises(AppError) as exc:
        await PolymarketSdkCredentialDeriver().create_or_derive_api_credentials(
            private_key=PRIVATE_KEY,
            chain_id=137,
            funder_address=None,
            signature_type=3,
        )

    assert exc.value.code == "WALLET_API_CREDENTIAL_DERIVATION_FAILED"


@pytest.mark.asyncio
async def test_fallback_derive_method_is_used_when_create_or_derive_fails(monkeypatch) -> None:
    fake_client = _install_fake_clob_client(
        monkeypatch,
        RuntimeError('status=400 body={"error":"Could not create api key"}'),
        fallback_response=ApiCredsLike(api_key="fallback-key", api_secret="fallback-secret", api_passphrase="fallback-pass"),
    )

    payload = await PolymarketSdkCredentialDeriver().create_or_derive_api_credentials(
        private_key=PRIVATE_KEY,
        chain_id=137,
        funder_address=None,
        signature_type=3,
    )

    assert payload["api_key"] == "fallback-key"
    assert fake_client.fallback_called is True


@pytest.mark.asyncio
async def test_sdk_invalid_signature_maps_to_specific_error(monkeypatch) -> None:
    _install_fake_clob_client(monkeypatch, RuntimeError("INVALID_SIGNATURE"))

    with pytest.raises(AppError) as exc:
        await PolymarketSdkCredentialDeriver().create_or_derive_api_credentials(
            private_key=PRIVATE_KEY,
            chain_id=137,
            funder_address=None,
            signature_type=3,
        )

    assert exc.value.code == "POLYMARKET_INVALID_SIGNATURE"


@pytest.mark.asyncio
async def test_no_secret_appears_in_logs(monkeypatch, caplog) -> None:
    caplog.set_level(logging.WARNING, logger="app.services.wallet_credentials")
    _install_fake_clob_client(monkeypatch, {"apiKey": "api-key", "secret": "very-secret"})

    with pytest.raises(AppError):
        await PolymarketSdkCredentialDeriver().create_or_derive_api_credentials(
            private_key=PRIVATE_KEY,
            chain_id=137,
            funder_address=None,
            signature_type=3,
        )

    logs = caplog.text
    assert PRIVATE_KEY not in logs
    assert "very-secret" not in logs


def test_test_derive_endpoint_returns_safe_status_only(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    app.dependency_overrides[get_api_credential_deriver] = lambda: FakeCredentialDeriver()
    try:
        with TestClient(app) as client:
            response = client.post("/api/wallet/test-derive", json={"private_key": PRIVATE_KEY})
    finally:
        app.dependency_overrides.clear()

    body = response.json()
    assert response.status_code == 200
    assert body["ok"] is True
    assert body["api_key_present"] is True
    assert body["secret_present"] is True
    assert body["passphrase_present"] is True
    assert "api-secret-one" not in response.text
    assert "api-passphrase-one" not in response.text
    assert PRIVATE_KEY not in response.text


@pytest.mark.asyncio
async def test_trading_bundle_requires_api_credentials(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        await configure_wallet(
            WalletConfigureRequest(private_key=PRIVATE_KEY, derive_api_credentials=False),
            session,
            deriver=FakeCredentialDeriver(),
        )
        with pytest.raises(AppError) as exc:
            await get_active_wallet_credentials_for_trading(session)

    assert exc.value.code == "WALLET_API_CREDENTIALS_MISSING"


async def get_active_wallet_credentials_for_trading_or_none(session: AsyncSession):
    try:
        return await get_active_wallet_credentials_for_trading(session)
    except AppError:
        return None


def _install_fake_clob_client(monkeypatch, response_or_exception, *, fallback_response=None):
    module = ModuleType("py_clob_client_v2")

    class FakeClobClient:
        last_kwargs = None
        fallback_called = False

        def __init__(self, **kwargs):
            type(self).last_kwargs = kwargs

        def create_or_derive_api_key(self):
            if isinstance(response_or_exception, Exception):
                raise response_or_exception
            return response_or_exception

        def derive_api_key(self):
            type(self).fallback_called = True
            if fallback_response is None:
                raise response_or_exception
            if isinstance(fallback_response, Exception):
                raise fallback_response
            return fallback_response

    module.ClobClient = FakeClobClient
    monkeypatch.setitem(sys.modules, "py_clob_client_v2", module)
    return FakeClobClient
