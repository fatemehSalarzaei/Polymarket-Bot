from __future__ import annotations

import argparse
import asyncio
import getpass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.models.user import User
from app.schemas.auth import USER_ROLE_VALUES
from app.services.auth import hash_password

MIN_PASSWORD_LENGTH = 10


async def main(default_role: str = "admin") -> None:
    default_role = validate_role(default_role)
    parser = argparse.ArgumentParser(description="Create the first admin or super user.")
    parser.add_argument("--email")
    parser.add_argument("--username")
    parser.add_argument("--password")
    parser.add_argument(
        "--role",
        default=default_role,
        choices=sorted(USER_ROLE_VALUES),
        help=f"User role. Default: {default_role}.",
    )
    parser.add_argument(
        "--update-role",
        action="store_true",
        help="Update the role if a user with this email or username already exists.",
    )
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="Reset the password if a user with this email or username already exists.",
    )
    args = parser.parse_args()

    settings = get_settings()
    email = normalize_email(args.email or settings.admin_email)
    username = normalize_username(args.username or settings.admin_username)

    if not email or not username:
        raise SystemExit("ADMIN_EMAIL and ADMIN_USERNAME are required, or pass --email and --username.")

    maker = get_sessionmaker()
    async with maker() as session:
        await create_or_update_admin_user(
            session,
            email=email,
            username=username,
            password=args.password,
            fallback_password_hash=settings.admin_password_hash,
            role=args.role,
            update_role=args.update_role,
            reset_password=args.reset_password,
        )


async def create_or_update_admin_user(
    session: AsyncSession,
    *,
    email: str,
    username: str,
    password: str | None,
    fallback_password_hash: str,
    role: str,
    update_role: bool = False,
    reset_password: bool = False,
) -> User:
    role = validate_role(role)
    existing_user = await find_user_by_email_or_username(session, email=email, username=username)

    if existing_user is None:
        password_hash = resolve_password_hash(password=password, fallback_password_hash=fallback_password_hash)
        user = User(
            email=email,
            username=username,
            password_hash=password_hash,
            role=role,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        print(f"Created admin user id={user.id} username={user.username} role={user.role}")
        return user

    changed = False
    if update_role and existing_user.role != role:
        existing_user.role = role
        changed = True
    if reset_password:
        existing_user.password_hash = resolve_password_hash(password=password, fallback_password_hash=fallback_password_hash)
        changed = True

    if not changed:
        print(
            "A user with that email or username already exists; no changes made. "
            "Use --update-role to change the role or --reset-password to reset the password."
        )
        print(
            f"Existing user id={existing_user.id} "
            f"username={existing_user.username} "
            f"email={existing_user.email} "
            f"role={existing_user.role}"
        )
        return existing_user

    session.add(existing_user)
    await session.commit()
    await session.refresh(existing_user)
    print(
        f"Updated admin user id={existing_user.id} "
        f"username={existing_user.username} "
        f"email={existing_user.email} "
        f"role={existing_user.role}"
    )
    return existing_user


async def find_user_by_email_or_username(session: AsyncSession, *, email: str, username: str) -> User | None:
    result = await session.execute(select(User).where(or_(User.email == email, User.username == username)))
    return result.scalar_one_or_none()


def resolve_password_hash(*, password: str | None, fallback_password_hash: str) -> str:
    if fallback_password_hash:
        return fallback_password_hash

    resolved_password = password or getpass.getpass("Admin password: ")
    if len(resolved_password) < MIN_PASSWORD_LENGTH:
        raise SystemExit(f"Admin password must be at least {MIN_PASSWORD_LENGTH} characters.")
    return hash_password(resolved_password)


def validate_role(role: str) -> str:
    if role not in USER_ROLE_VALUES:
        raise SystemExit(f"Invalid role '{role}'. Allowed roles: {', '.join(sorted(USER_ROLE_VALUES))}.")
    return role


def normalize_email(email: str | None) -> str:
    email = (email or "").strip().lower()
    if email and "@" not in email:
        raise SystemExit("Email is invalid.")
    return email


def normalize_username(username: str | None) -> str:
    return (username or "").strip()


if __name__ == "__main__":
    asyncio.run(main())
