from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings
from app.core.errors import AppError


def encrypt_secret(value: str) -> str:
    if value == "":
        return ""
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise AppError("WALLET_DECRYPTION_FAILED", status_code=500) from exc


def mask_secret(value: str, *, kind: str = "generic") -> str:
    if not value:
        return ""
    if kind == "private_key" and value.startswith("0x") and len(value) >= 10:
        return f"{value[:6]}...{value[-4:]}"
    if kind == "api_key" and len(value) >= 10:
        return f"{value[:6]}...{value[-4:]}"
    if len(value) <= 4:
        return "****"
    return "****"


def validate_encryption_key_for_startup() -> None:
    settings = get_settings()
    if settings.app_env.lower() == "production":
        _fernet()


def _fernet() -> Fernet:
    key = get_settings().credential_encryption_key
    if not key:
        raise AppError("WALLET_ENCRYPTION_KEY_MISSING", status_code=500)
    try:
        return Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise AppError("WALLET_ENCRYPTION_KEY_MISSING", technical_detail="Invalid Fernet key", status_code=500) from exc
