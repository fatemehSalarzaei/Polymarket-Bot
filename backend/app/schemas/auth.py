from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

UserRole = Literal["admin", "trader", "viewer"]


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    ok: bool
    user: "UserResponse"
    expires_in_minutes: int


class CurrentUserResponse(BaseModel):
    authenticated: bool
    user: "UserResponse | None" = None


class CreateUserRequest(BaseModel):
    email: str
    username: str = Field(min_length=2, max_length=128)
    password: str = Field(min_length=10)
    role: UserRole = "trader"
    is_active: bool = True


class UpdateUserRequest(BaseModel):
    email: str | None = None
    username: str | None = Field(default=None, min_length=2, max_length=128)
    role: UserRole | None = None
    is_active: bool | None = None


class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None

    model_config = {"from_attributes": True}


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10)


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=10)
