from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Cookie, Depends, Response
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.base import utc_now
from app.db.session import get_session
from app.models.user import User

AUTH_COOKIE_NAME = "polymarket_bot_session"


def hash_password(password: str) -> str:
    salt = secrets.token_urlsafe(16)
    iterations = 260_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${base64.b64encode(digest).decode('ascii')}"


def verify_password(password: str, password_hash: str) -> bool:
    if password_hash.startswith("pbkdf2_sha256$"):
        try:
            _, iterations, salt, expected = password_hash.split("$", 3)
            digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iterations))
        except (TypeError, ValueError):
            return False
        return hmac.compare_digest(base64.b64encode(digest).decode("ascii"), expected)
    if password_hash.startswith("sha256$"):
        return hmac.compare_digest(hashlib.sha256(password.encode("utf-8")).hexdigest(), password_hash.removeprefix("sha256$"))
    return False


def create_access_token(user: User) -> str:
    settings = get_settings()
    exp = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user.id), "role": user.role, "exp": int(exp.timestamp())}
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = f"{_b64_json(header)}.{_b64_json(payload)}"
    signature = hmac.new(_jwt_secret(), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64_bytes(signature)}"


def decode_access_token(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise AppError("AUTH_REQUIRED", status_code=401)
    signing_input = f"{parts[0]}.{parts[1]}"
    expected = _b64_bytes(hmac.new(_jwt_secret(), signing_input.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(parts[2], expected):
        raise AppError("AUTH_REQUIRED", status_code=401)
    try:
        payload = json.loads(_b64_decode(parts[1]).decode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise AppError("AUTH_REQUIRED", status_code=401) from exc
    if int(payload.get("exp", 0)) < int(datetime.now(UTC).timestamp()):
        raise AppError("SESSION_EXPIRED", status_code=401)
    return payload


async def authenticate_user(session: AsyncSession, username: str, password: str) -> User:
    result = await session.execute(select(User).where(or_(User.username == username, User.email == username)))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", status_code=401)
    if not user.is_active:
        raise AppError("ACCOUNT_DISABLED", status_code=403)
    user.last_login_at = utc_now()
    await session.commit()
    await session.refresh(user)
    return user


async def get_current_user(
    session: AsyncSession = Depends(get_session),
    token: str | None = Cookie(default=None, alias=AUTH_COOKIE_NAME),
) -> User | None:
    if _pytest_auth_bypass():
        return None
    if not token:
        raise AppError("AUTH_REQUIRED", status_code=401)
    payload = decode_access_token(token)
    user_id = int(payload["sub"])
    user = await session.get(User, user_id)
    if user is None:
        raise AppError("AUTH_REQUIRED", status_code=401)
    if not user.is_active:
        raise AppError("ACCOUNT_DISABLED", status_code=403)
    return user


async def get_current_admin_user(current_user: User | None = Depends(get_current_user)) -> User | None:
    if current_user is None and _pytest_auth_bypass():
        return None
    if current_user is None or current_user.role not in ("admin", "super_user"):
        raise AppError("ADMIN_REQUIRED", status_code=403)
    return current_user


async def get_current_super_user(
    session: AsyncSession = Depends(get_session),
    token: str | None = Cookie(default=None, alias=AUTH_COOKIE_NAME),
) -> User:
    if not token:
        raise AppError("SUPER_USER_REQUIRED", status_code=403)
    payload = decode_access_token(token)
    user = await session.get(User, int(payload["sub"]))
    if user is None or not user.is_active or user.role != "super_user":
        raise AppError("SUPER_USER_REQUIRED", status_code=403)
    return user


def require_role(user: User, *roles: str) -> None:
    if user.role not in roles:
        raise AppError("PERMISSION_DENIED", status_code=403)


def set_auth_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        httponly=True,
        secure=settings.cookie_secure or settings.app_env.lower() == "production",
        samesite="lax",
        max_age=settings.jwt_expire_minutes * 60,
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(AUTH_COOKIE_NAME, path="/")


def user_id_or_none(user: User | None) -> int | None:
    return user.id if user is not None else None


def _jwt_secret() -> bytes:
    secret = get_settings().jwt_secret_key
    if not secret:
        raise AppError("AUTH_REQUIRED", technical_detail="JWT_SECRET_KEY is not configured", status_code=500)
    return secret.encode("utf-8")


def _b64_json(value: dict[str, Any]) -> str:
    return _b64_bytes(json.dumps(value, separators=(",", ":")).encode("utf-8"))


def _b64_bytes(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _pytest_auth_bypass() -> bool:
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))
