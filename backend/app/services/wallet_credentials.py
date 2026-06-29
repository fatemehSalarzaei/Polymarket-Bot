from __future__ import annotations

import asyncio
import importlib.metadata
import logging
import re
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from Crypto.Hash import keccak
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.base import utc_now
from app.models.wallet import WalletCredential
from app.schemas.wallet import (
    WalletConfigureRequest,
    WalletReadinessResponse,
    WalletResponse,
    WalletTestDeriveResponse,
    WalletTestResponse,
)
from app.services.secret_crypto import decrypt_secret, encrypt_secret, mask_secret

logger = logging.getLogger(__name__)


class ApiCredentialDeriver(Protocol):
    async def create_or_derive_api_credentials(
        self,
        *,
        private_key: str,
        chain_id: int,
        funder_address: str | None,
        signature_type: int,
    ) -> dict[str, str]:
        ...


@dataclass(frozen=True)
class TradingCredentialBundle:
    wallet_credential_id: int
    private_key: str
    wallet_address: str
    funder_address: str | None
    signature_type: int
    chain_id: int
    api_key: str
    api_secret: str
    api_passphrase: str


class PolymarketSdkCredentialDeriver:
    async def create_or_derive_api_credentials(
        self,
        *,
        private_key: str,
        chain_id: int,
        funder_address: str | None,
        signature_type: int,
    ) -> dict[str, str]:
        wallet_address = derive_wallet_address(private_key)
        settings = get_settings()
        host = str(settings.polymarket_clob_host).rstrip("/")
        sdk_version = _sdk_version()
        try:
            from py_clob_client_v2 import ClobClient  # type: ignore
        except ImportError as exc:
            _log_derivation_failure(
                exc,
                wallet_address=wallet_address,
                host=host,
                chain_id=chain_id,
                private_key_valid=True,
                sdk_version=sdk_version,
            )
            raise AppError(
                "POLYMARKET_SDK_MISSING",
                technical_detail="py_clob_client_v2 is not installed or cannot be imported.",
                status_code=503,
            ) from exc

        try:
            credentials = await asyncio.to_thread(_derive_credentials_sync, ClobClient, host, chain_id, private_key)
        except Exception as exc:
            _log_derivation_failure(
                exc,
                wallet_address=wallet_address,
                host=host,
                chain_id=chain_id,
                private_key_valid=True,
                sdk_version=sdk_version,
            )
            raise _map_derivation_exception(exc) from exc

        try:
            payload = normalize_polymarket_api_creds(credentials)
        except AppError as exc:
            logger.warning(
                "wallet_api_credential_response_invalid",
                extra={
                    "wallet_address": wallet_address,
                    "host": host,
                    "chain_id": chain_id,
                    "validation_passed": True,
                    "sdk_version": sdk_version,
                    "response_type": _credential_type(credentials),
                    "response_fields": _credential_public_fields(credentials),
                },
            )
            raise exc
        logger.info(
            "wallet_api_credentials_derived",
            extra={
                "wallet_address": wallet_address,
                "host": host,
                "chain_id": chain_id,
                "validation_passed": True,
                "sdk_version": sdk_version,
                "credential_response_type": _credential_type(credentials),
                "credential_response_fields": _credential_public_fields(credentials),
            },
        )
        return payload


async def configure_wallet(
    request: WalletConfigureRequest,
    session: AsyncSession,
    *,
    deriver: ApiCredentialDeriver | None = None,
    user_id: int | None = None,
) -> WalletCredential:
    private_key = validate_private_key(request.private_key)
    wallet_address = derive_wallet_address(private_key)
    api_credentials: dict[str, str] | None = None
    last_error = None
    if request.derive_api_credentials:
        api_credentials = await (deriver or PolymarketSdkCredentialDeriver()).create_or_derive_api_credentials(
            private_key=private_key,
            chain_id=request.chain_id,
            funder_address=request.funder_address,
            signature_type=request.signature_type,
        )

    existing = await _active_wallet(session, user_id=user_id)
    now = utc_now()
    if existing is None:
        credential = WalletCredential(
            wallet_address=wallet_address,
            user_id=user_id,
            funder_address=request.funder_address,
            signature_type=request.signature_type,
            chain_id=request.chain_id,
            encrypted_private_key=encrypt_secret(private_key),
            is_configured=True,
            is_active=True,
            last_error=last_error,
            created_at=now,
            updated_at=now,
        )
        session.add(credential)
    else:
        credential = existing
        credential.wallet_address = wallet_address
        credential.funder_address = request.funder_address
        credential.signature_type = request.signature_type
        credential.chain_id = request.chain_id
        credential.encrypted_private_key = encrypt_secret(private_key)
        credential.is_configured = True
        credential.is_active = True
        credential.last_error = last_error
        credential.updated_at = now

    if api_credentials is not None:
        _apply_api_credentials(credential, api_credentials, now=now)
    else:
        credential.encrypted_api_key = None
        credential.encrypted_api_secret = None
        credential.encrypted_api_passphrase = None
        credential.api_credentials_created_at = None

    await _deactivate_duplicate_wallets(session, keep_id=credential.id, user_id=user_id)
    await session.commit()
    await session.refresh(credential)
    return credential


async def get_wallet_status(session: AsyncSession, *, user_id: int | None = None) -> WalletResponse:
    credential = await _active_wallet(session, user_id=user_id)
    return wallet_response(credential)


async def derive_api_credentials(
    session: AsyncSession,
    *,
    deriver: ApiCredentialDeriver | None = None,
    user_id: int | None = None,
) -> WalletCredential:
    credential = await _active_wallet(session, user_id=user_id)
    if credential is None or not credential.is_configured:
        raise AppError("WALLET_CONFIG_MISSING", status_code=404)
    private_key = decrypt_secret(credential.encrypted_private_key)
    api_credentials = await (deriver or PolymarketSdkCredentialDeriver()).create_or_derive_api_credentials(
        private_key=private_key,
        chain_id=credential.chain_id,
        funder_address=credential.funder_address,
        signature_type=credential.signature_type,
    )
    now = utc_now()
    _apply_api_credentials(credential, api_credentials, now=now)
    credential.last_error = None
    credential.updated_at = now
    await session.commit()
    await session.refresh(credential)
    return credential


async def test_derive_api_credentials(
    request: WalletConfigureRequest,
    *,
    deriver: ApiCredentialDeriver | None = None,
) -> WalletTestDeriveResponse:
    private_key = validate_private_key(request.private_key)
    wallet_address = derive_wallet_address(private_key)
    credentials = await (deriver or PolymarketSdkCredentialDeriver()).create_or_derive_api_credentials(
        private_key=private_key,
        chain_id=request.chain_id,
        funder_address=request.funder_address,
        signature_type=request.signature_type,
    )
    return WalletTestDeriveResponse(
        ok=True,
        wallet_address=wallet_address,
        api_key_present=bool(credentials.get("api_key")),
        secret_present=bool(credentials.get("api_secret")),
        passphrase_present=bool(credentials.get("api_passphrase")),
    )


async def test_wallet_credentials(session: AsyncSession, *, user_id: int | None = None) -> WalletTestResponse:
    credential = await _active_wallet(session, user_id=user_id)
    issues: list[str] = []
    if credential is None or not credential.is_configured:
        issues.append("WALLET_CONFIG_MISSING")
        return WalletTestResponse(
            ok=False,
            message="Wallet is not configured.",
            wallet_address=None,
            api_key_configured=False,
            trading_ready=False,
            issues=issues,
        )
    api_key_configured = _api_credentials_configured(credential)
    if not api_key_configured:
        issues.append("WALLET_API_CREDENTIALS_MISSING")
    try:
        decrypt_secret(credential.encrypted_private_key)
        if credential.encrypted_api_secret:
            decrypt_secret(credential.encrypted_api_secret)
        if credential.encrypted_api_passphrase:
            decrypt_secret(credential.encrypted_api_passphrase)
    except AppError:
        issues.append("WALLET_DECRYPTION_FAILED")
    credential.last_validated_at = utc_now()
    credential.last_error = ", ".join(issues) if issues else None
    await session.commit()
    return WalletTestResponse(
        ok=not issues,
        message="Wallet credentials are configured." if not issues else "Wallet credentials need attention.",
        wallet_address=credential.wallet_address,
        api_key_configured=api_key_configured,
        trading_ready=not issues,
        issues=issues,
    )


async def get_active_wallet_credentials_for_trading(session: AsyncSession, *, user_id: int | None = None) -> TradingCredentialBundle:
    credential = await _active_wallet(session, user_id=user_id)
    if credential is None or not credential.is_configured:
        raise AppError("WALLET_CONFIG_MISSING", status_code=403)
    if not _api_credentials_configured(credential):
        raise AppError("WALLET_API_CREDENTIALS_MISSING", status_code=403)
    return TradingCredentialBundle(
        wallet_credential_id=credential.id,
        private_key=decrypt_secret(credential.encrypted_private_key),
        wallet_address=credential.wallet_address,
        funder_address=credential.funder_address,
        signature_type=credential.signature_type,
        chain_id=credential.chain_id,
        api_key=decrypt_secret(credential.encrypted_api_key or ""),
        api_secret=decrypt_secret(credential.encrypted_api_secret or ""),
        api_passphrase=decrypt_secret(credential.encrypted_api_passphrase or ""),
    )


async def delete_wallet_credentials(session: AsyncSession, *, user_id: int | None = None) -> None:
    statement = delete(WalletCredential)
    if user_id is not None:
        statement = statement.where(WalletCredential.user_id == user_id)
    await session.execute(statement)
    await session.commit()


def wallet_response(credential: WalletCredential | None) -> WalletResponse:
    if credential is None or not credential.is_configured:
        return WalletResponse(configured=False, api_key_configured=False)
    api_key = decrypt_secret(credential.encrypted_api_key) if credential.encrypted_api_key else None
    return WalletResponse(
        configured=True,
        wallet_address=credential.wallet_address,
        funder_address=credential.funder_address,
        signature_type=credential.signature_type,
        chain_id=credential.chain_id,
        api_key_configured=_api_credentials_configured(credential),
        api_key_masked=mask_secret(api_key, kind="api_key") if api_key else None,
        last_validated_at=credential.last_validated_at,
        last_error=credential.last_error,
        updated_at=credential.updated_at,
    )


async def get_wallet_readiness(session: AsyncSession, *, user_id: int | None = None) -> WalletReadinessResponse:
    blocking_reasons: list[str] = []
    credential = await _active_wallet(session, user_id=user_id)
    if credential is None or not credential.is_configured:
        blocking_reasons.append("WALLET_CONFIG_MISSING")
        return WalletReadinessResponse(
            wallet_configured=False,
            api_credentials_configured=False,
            private_key_decryptable=False,
            funder_address_configured=False,
            trading_ready=False,
            blocking_reasons=blocking_reasons,
        )

    private_key_decryptable = False
    try:
        decrypt_secret(credential.encrypted_private_key)
        private_key_decryptable = True
    except AppError:
        blocking_reasons.append("WALLET_DECRYPTION_FAILED")

    api_credentials_configured = _api_credentials_configured(credential)
    if not api_credentials_configured:
        blocking_reasons.append("WALLET_API_CREDENTIALS_MISSING")
    if credential.chain_id != 137:
        blocking_reasons.append("WALLET_CHAIN_ID_INVALID")
    if credential.signature_type == 3 and not credential.funder_address:
        blocking_reasons.append("WALLET_FUNDER_REQUIRED")

    return WalletReadinessResponse(
        wallet_configured=True,
        api_credentials_configured=api_credentials_configured,
        private_key_decryptable=private_key_decryptable,
        funder_address_configured=bool(credential.funder_address),
        signature_type=credential.signature_type,
        chain_id=credential.chain_id,
        trading_ready=not blocking_reasons,
        blocking_reasons=list(dict.fromkeys(blocking_reasons)),
    )


def validate_private_key(private_key: str) -> str:
    private_key = private_key.strip()
    if not private_key.startswith("0x") or len(private_key) != 66:
        raise AppError("WALLET_PRIVATE_KEY_INVALID", status_code=422)
    try:
        value = int(private_key[2:], 16)
        if value <= 0:
            raise ValueError("private key must be greater than zero")
        _account_from_private_key(private_key)
    except Exception as exc:
        raise AppError("WALLET_PRIVATE_KEY_INVALID", status_code=422) from exc
    return private_key


def derive_wallet_address(private_key: str) -> str:
    private_key = validate_private_key(private_key)
    account = _account_from_private_key(private_key)
    if account is not None:
        return str(account.address)
    private_value = int(private_key[2:], 16)
    try:
        private = ec.derive_private_key(private_value, ec.SECP256K1())
        numbers = private.public_key().public_numbers()
    except ValueError as exc:
        raise AppError("WALLET_PRIVATE_KEY_INVALID", status_code=422) from exc
    public_key = numbers.x.to_bytes(32, "big") + numbers.y.to_bytes(32, "big")
    digest = keccak.new(digest_bits=256)
    digest.update(public_key)
    address = digest.digest()[-20:].hex()
    return _checksum_address(address)


def _checksum_address(address: str) -> str:
    lower = address.lower()
    digest = keccak.new(digest_bits=256)
    digest.update(lower.encode("ascii"))
    hash_hex = digest.hexdigest()
    checksummed = "".join(char.upper() if int(hash_hex[index], 16) >= 8 else char for index, char in enumerate(lower))
    return f"0x{checksummed}"


async def _active_wallet(session: AsyncSession, *, user_id: int | None = None) -> WalletCredential | None:
    statement = select(WalletCredential).where(WalletCredential.is_active.is_(True))
    if user_id is not None:
        statement = statement.where(WalletCredential.user_id == user_id)
    result = await session.execute(statement.limit(1))
    return result.scalar_one_or_none()


async def _deactivate_duplicate_wallets(session: AsyncSession, *, keep_id: int | None, user_id: int | None = None) -> None:
    if keep_id is None:
        return
    statement = select(WalletCredential).where(WalletCredential.id != keep_id)
    if user_id is not None:
        statement = statement.where(WalletCredential.user_id == user_id)
    result = await session.execute(statement)
    for credential in result.scalars():
        credential.is_active = False


def _apply_api_credentials(credential: WalletCredential, credentials: dict[str, str], *, now) -> None:
    credential.encrypted_api_key = encrypt_secret(credentials["api_key"])
    credential.encrypted_api_secret = encrypt_secret(credentials["api_secret"])
    credential.encrypted_api_passphrase = encrypt_secret(credentials["api_passphrase"])
    credential.api_credentials_created_at = now


def _api_credentials_configured(credential: WalletCredential) -> bool:
    return bool(credential.encrypted_api_key and credential.encrypted_api_secret and credential.encrypted_api_passphrase)


def normalize_polymarket_api_creds(creds: Any) -> dict[str, str]:
    payload = {
        "api_key": _read_credential_field(creds, "apiKey", "key", "api_key"),
        "api_secret": _read_credential_field(creds, "secret", "api_secret"),
        "api_passphrase": _read_credential_field(creds, "passphrase", "api_passphrase"),
    }
    if not payload["api_key"] or not payload["api_secret"] or not payload["api_passphrase"]:
        raise AppError(
            "WALLET_API_CREDENTIAL_RESPONSE_INVALID",
            technical_detail=(
                f"Polymarket SDK response type: {_credential_type(creds)}; "
                f"public fields: {_credential_public_fields(creds)}"
            ),
            status_code=503,
        )
    return payload


def _read_credential_field(creds: Any, *names: str) -> str:
    for name in names:
        if isinstance(creds, dict) and creds.get(name):
            return str(creds[name])
        if hasattr(creds, name):
            value = getattr(creds, name)
            if value:
                return str(value)
    return ""


def _derive_credentials_sync(clob_client_class, host: str, chain_id: int, private_key: str) -> Any:
    client = clob_client_class(host=host, chain_id=chain_id, key=private_key)
    try:
        return client.create_or_derive_api_key()
    except Exception:
        for method_name in ("derive_api_key", "derive_api_creds", "get_api_keys"):
            if not hasattr(client, method_name):
                continue
            fallback = getattr(client, method_name)
            if callable(fallback):
                return fallback()
        raise


def _map_derivation_exception(exc: Exception) -> AppError:
    detail = _safe_exception_detail(exc)
    upper_detail = detail.upper()
    status_code = getattr(getattr(exc, "response", None), "status_code", None) or getattr(exc, "status_code", None)
    if "INVALID_SIGNATURE" in upper_detail:
        return AppError("POLYMARKET_INVALID_SIGNATURE", technical_detail=detail, status_code=401)
    if status_code in {401, 403}:
        return AppError("POLYMARKET_AUTH_REJECTED", technical_detail=detail, status_code=403)
    if _is_network_exception(exc):
        return AppError("POLYMARKET_AUTH_NETWORK_ERROR", technical_detail=detail, status_code=503)
    return AppError("WALLET_API_CREDENTIAL_DERIVATION_FAILED", technical_detail=detail, status_code=503)


def _is_network_exception(exc: Exception) -> bool:
    if isinstance(exc, (TimeoutError, ConnectionError, httpx.TimeoutException, httpx.NetworkError)):
        return True
    module = type(exc).__module__
    name = type(exc).__name__.lower()
    return "requests" in module and any(part in name for part in ("timeout", "connection", "network"))


def _credential_type(credentials: Any) -> str:
    return f"{type(credentials).__module__}.{type(credentials).__name__}"


def _credential_public_fields(credentials: Any) -> list[str]:
    if isinstance(credentials, dict):
        return sorted(str(key) for key in credentials.keys())
    if hasattr(credentials, "__dict__"):
        return sorted(str(key) for key in vars(credentials).keys() if not str(key).startswith("_"))
    fields: list[str] = []
    for name in dir(credentials):
        if name.startswith("_"):
            continue
        try:
            value = getattr(type(credentials), name, None)
        except Exception:
            value = None
        if isinstance(value, property):
            fields.append(name)
    return sorted(fields)


def _log_derivation_failure(
    exc: Exception,
    *,
    wallet_address: str,
    host: str,
    chain_id: int,
    private_key_valid: bool,
    sdk_version: str | None,
) -> None:
    logger.warning(
        "wallet_api_credential_derivation_failed",
        extra={
            "exception_class": type(exc).__name__,
            "exception_message": _safe_exception_detail(exc),
            "wallet_address": wallet_address,
            "host": host,
            "chain_id": chain_id,
            "validation_passed": private_key_valid,
            "sdk_version": sdk_version,
        },
    )


def _sdk_version() -> str | None:
    for package in ("py-clob-client-v2", "py_clob_client_v2"):
        try:
            return importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            continue
    return None


def _account_from_private_key(private_key: str):
    try:
        from eth_account import Account
    except ImportError:
        return None
    return Account.from_key(private_key)


def _safe_exception_detail(exc: Exception) -> str:
    text = str(exc)
    text = re.sub(r"0x[a-fA-F0-9]{64}", "[redacted_private_key]", text)
    settings = get_settings()
    for secret in (
        settings.private_key,
        settings.polymarket_api_key,
        settings.polymarket_api_secret,
        settings.polymarket_api_passphrase,
    ):
        if secret:
            text = text.replace(secret, "[redacted]")
    return text[:500]
