from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.session import get_session
from app.models.audit import AuditLog
from app.models.market import Market
from app.models.order import Order
from app.models.redeem import RedeemRecord
from app.models.settings import StrategySettings
from app.models.settlement import Settlement
from app.models.strategy import StrategyDecision
from app.models.user import User
from app.models.wallet import WalletCredential
from app.schemas.auth import USER_ROLE_OPTIONS, CreateUserRequest, ResetPasswordRequest, UpdateUserRequest, UserResponse
from app.schemas.wallet import WalletResponse
from app.services.auth import get_current_admin_user, hash_password
from app.services.auth import get_current_super_user
from app.services.wallet_credentials import wallet_response

router = APIRouter()

TABLES: dict[str, Any] = {
    "users": User,
    "markets": Market,
    "strategy_settings": StrategySettings,
    "strategy_decisions": StrategyDecision,
    "orders": Order,
    "settlements": Settlement,
    "redeem_records": RedeemRecord,
    "audit_logs": AuditLog,
}


@router.get("/admin/users", response_model=list[UserResponse])
async def list_users(
    session: AsyncSession = Depends(get_session),
    admin: User | None = Depends(get_current_admin_user),
) -> list[UserResponse]:
    result = await session.execute(select(User).order_by(User.id))
    return [UserResponse.model_validate(user) for user in result.scalars().all()]


@router.post("/admin/users", response_model=UserResponse)
async def create_user(
    payload: CreateUserRequest,
    session: AsyncSession = Depends(get_session),
    admin: User | None = Depends(get_current_super_user),
) -> UserResponse:
    user = User(
        email=payload.email.strip().lower(),
        username=payload.username.strip(),
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=payload.is_active,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return UserResponse.model_validate(user)


@router.get("/admin/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    admin: User | None = Depends(get_current_admin_user),
) -> UserResponse:
    return UserResponse.model_validate(await _user_or_404(session, user_id))


@router.patch("/admin/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    payload: UpdateUserRequest,
    session: AsyncSession = Depends(get_session),
    admin: User | None = Depends(get_current_super_user),
) -> UserResponse:
    user = await _user_or_404(session, user_id)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(user, key, value.strip().lower() if key == "email" and isinstance(value, str) else value)
    await session.commit()
    await session.refresh(user)
    return UserResponse.model_validate(user)


@router.post("/admin/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    payload: ResetPasswordRequest,
    session: AsyncSession = Depends(get_session),
    admin: User | None = Depends(get_current_super_user),
) -> dict[str, bool]:
    user = await _user_or_404(session, user_id)
    user.password_hash = hash_password(payload.new_password)
    await session.commit()
    return {"ok": True}


@router.post("/admin/users/{user_id}/disable")
async def disable_user(user_id: int, session: AsyncSession = Depends(get_session), admin: User | None = Depends(get_current_super_user)) -> dict[str, bool]:
    user = await _user_or_404(session, user_id)
    user.is_active = False
    await session.commit()
    return {"ok": True}


@router.post("/admin/users/{user_id}/enable")
async def enable_user(user_id: int, session: AsyncSession = Depends(get_session), admin: User | None = Depends(get_current_super_user)) -> dict[str, bool]:
    user = await _user_or_404(session, user_id)
    user.is_active = True
    await session.commit()
    return {"ok": True}


@router.get("/admin/tables")
async def list_allowed_tables(admin: User | None = Depends(get_current_admin_user)) -> dict[str, list[str]]:
    return {"tables": [*TABLES.keys(), "wallet_credentials_masked"]}


@router.get("/admin/roles")
async def list_roles(admin: User | None = Depends(get_current_admin_user)) -> dict[str, list[dict[str, str]]]:
    return {"roles": [*USER_ROLE_OPTIONS]}


@router.get("/admin/tables/{table_name}")
async def browse_table(
    table_name: str,
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    admin: User | None = Depends(get_current_admin_user),
) -> list[dict[str, Any]]:
    if table_name == "wallet_credentials_masked":
        result = await session.execute(select(WalletCredential).order_by(WalletCredential.id).limit(limit))
        return [_masked_wallet(row) for row in result.scalars().all()]
    model = TABLES.get(table_name)
    if model is None:
        raise AppError("PERMISSION_DENIED", technical_detail="Table is not allowlisted", status_code=403)
    result = await session.execute(select(model).order_by(model.id).limit(limit))
    return [_public_row(row) for row in result.scalars().all()]


@router.get("/admin/users/{user_id}/wallet", response_model=WalletResponse)
async def get_user_wallet(user_id: int, session: AsyncSession = Depends(get_session), admin: User | None = Depends(get_current_admin_user)) -> WalletResponse:
    result = await session.execute(select(WalletCredential).where(WalletCredential.user_id == user_id, WalletCredential.is_active.is_(True)).limit(1))
    return wallet_response(result.scalar_one_or_none())


@router.get("/admin/audit-logs")
async def get_admin_audit_logs(limit: int = Query(default=100, ge=1, le=500), session: AsyncSession = Depends(get_session), admin: User | None = Depends(get_current_admin_user)) -> list[dict[str, Any]]:
    result = await session.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit))
    return [_public_row(row) for row in result.scalars().all()]


async def _user_or_404(session: AsyncSession, user_id: int) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise AppError("HTTP_ERROR", technical_detail="USER_NOT_FOUND", status_code=404)
    return user


def _public_row(row: Any) -> dict[str, Any]:
    payload = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    for secret in (
        "password_hash",
        "encrypted_private_key",
        "encrypted_api_key",
        "encrypted_api_secret",
        "encrypted_api_passphrase",
        "private_key",
        "api_secret",
        "api_passphrase",
        "credential_encryption_key",
        "jwt_secret_key",
    ):
        payload.pop(secret, None)
    return payload


def _masked_wallet(row: WalletCredential) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "wallet_address": row.wallet_address,
        "funder_address": row.funder_address,
        "signature_type": row.signature_type,
        "chain_id": row.chain_id,
        "api_key_configured": bool(row.encrypted_api_key),
        "is_configured": row.is_configured,
        "is_active": row.is_active,
        "last_validated_at": row.last_validated_at,
        "last_error": row.last_error,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
