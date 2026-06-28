from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_session
from app.models.user import User
from app.schemas.auth import ChangePasswordRequest, CurrentUserResponse, LoginRequest, LoginResponse, UserResponse
from app.services.auth import (
    authenticate_user,
    clear_auth_cookie,
    create_access_token,
    get_current_user,
    hash_password,
    set_auth_cookie,
    verify_password,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/auth/login", response_model=LoginResponse)
async def login(payload: LoginRequest, response: Response, session: AsyncSession = Depends(get_session)) -> LoginResponse:
    user = await authenticate_user(session, payload.username, payload.password)
    set_auth_cookie(response, create_access_token(user))
    logger.info("auth_login_success", extra={"user_id": user.id, "role": user.role})
    return LoginResponse(
        ok=True,
        user=UserResponse.model_validate(user),
        expires_in_minutes=get_settings().jwt_expire_minutes,
    )


@router.post("/auth/logout")
async def logout(response: Response, current_user: User | None = Depends(get_current_user)) -> dict[str, bool]:
    logger.info("auth_logout", extra={"user_id": current_user.id if current_user is not None else None})
    clear_auth_cookie(response)
    return {"ok": True}


@router.get("/auth/me", response_model=CurrentUserResponse)
async def me(current_user: User | None = Depends(get_current_user)) -> CurrentUserResponse:
    if current_user is None:
        return CurrentUserResponse(authenticated=False, user=None)
    return CurrentUserResponse(authenticated=True, user=UserResponse.model_validate(current_user))


@router.post("/auth/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User | None = Depends(get_current_user),
) -> dict[str, bool]:
    if current_user is None:
        return {"ok": True}
    if not verify_password(payload.current_password, current_user.password_hash):
        from app.core.errors import AppError

        raise AppError("INVALID_CREDENTIALS", status_code=401)
    current_user.password_hash = hash_password(payload.new_password)
    session.add(current_user)
    await session.commit()
    return {"ok": True}
