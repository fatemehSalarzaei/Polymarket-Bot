from __future__ import annotations

import argparse
import asyncio
import getpass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_sessionmaker
from app.models.user import User
from app.schemas.auth import UserRole, USER_ROLE_VALUES
from app.services.auth import hash_password


VALID_ROLES = USER_ROLE_VALUES
MIN_PASSWORD_LENGTH = 10


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="polymarket",
        description="Polymarket Bot management commands.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    create_admin_parser = subparsers.add_parser(
        "create-admin",
        help="Create an admin user, similar to Django createsuperuser.",
    )
    create_admin_parser.add_argument("--username", required=True)
    create_admin_parser.add_argument("--email", required=True)
    create_admin_parser.add_argument("--password", required=False)
    create_admin_parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Update password/role if a user with this username or email already exists.",
    )

    create_user_parser = subparsers.add_parser(
        "create-user",
        help="Create a regular user.",
    )
    create_user_parser.add_argument("--username", required=True)
    create_user_parser.add_argument("--email", required=True)
    create_user_parser.add_argument("--password", required=False)
    create_user_parser.add_argument(
        "--role",
        default="trader",
        choices=sorted(VALID_ROLES),
        help="User role. Default: trader.",
    )
    create_user_parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Update password/role if a user with this username or email already exists.",
    )

    reset_password_parser = subparsers.add_parser(
        "reset-password",
        help="Reset a user's password.",
    )
    reset_password_parser.add_argument("--username", required=False)
    reset_password_parser.add_argument("--email", required=False)
    reset_password_parser.add_argument("--password", required=False)

    list_users_parser = subparsers.add_parser(
        "list-users",
        help="List users without exposing password hashes.",
    )
    list_users_parser.add_argument(
        "--include-disabled",
        action="store_true",
        help="Include inactive users.",
    )

    args = parser.parse_args()

    if args.command == "create-admin":
        asyncio.run(
            create_or_update_user_command(
                username=args.username,
                email=args.email,
                password=args.password,
                role="admin",
                replace_existing=args.replace_existing,
            )
        )
        return

    if args.command == "create-user":
        asyncio.run(
            create_or_update_user_command(
                username=args.username,
                email=args.email,
                password=args.password,
                role=args.role,
                replace_existing=args.replace_existing,
            )
        )
        return

    if args.command == "reset-password":
        if not args.username and not args.email:
            raise SystemExit("Provide --username or --email.")
        asyncio.run(
            reset_password_command(
                username=args.username,
                email=args.email,
                password=args.password,
            )
        )
        return

    if args.command == "list-users":
        asyncio.run(list_users_command(include_disabled=args.include_disabled))
        return

    raise SystemExit(f"Unknown command: {args.command}")


async def create_or_update_user_command(
    *,
    username: str,
    email: str,
    password: str | None,
    role: UserRole,
    replace_existing: bool,
) -> None:
    username = normalize_username(username)
    email = normalize_email(email)
    password = resolve_password(password)

    maker = get_sessionmaker()
    async with maker() as session:
        existing_user = await find_user_by_username_or_email(
            session,
            username=username,
            email=email,
        )

        if existing_user is not None and not replace_existing:
            raise SystemExit(
                "A user with this username or email already exists. "
                "Use --replace-existing to update it."
            )

        if existing_user is None:
            user = User(
                username=username,
                email=email,
                password_hash=hash_password(password),
                role=role,
                is_active=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            print(
                f"Created user id={user.id} "
                f"username={user.username} "
                f"email={user.email} "
                f"role={user.role}"
            )
            return

        existing_user.username = username
        existing_user.email = email
        existing_user.password_hash = hash_password(password)
        existing_user.role = role
        existing_user.is_active = True
        session.add(existing_user)
        await session.commit()
        await session.refresh(existing_user)
        print(
            f"Updated user id={existing_user.id} "
            f"username={existing_user.username} "
            f"email={existing_user.email} "
            f"role={existing_user.role}"
        )


async def reset_password_command(
    *,
    username: str | None,
    email: str | None,
    password: str | None,
) -> None:
    password = resolve_password(password)

    maker = get_sessionmaker()
    async with maker() as session:
        user = await find_user(session, username=username, email=email)
        if user is None:
            raise SystemExit("User not found.")

        user.password_hash = hash_password(password)
        user.is_active = True
        session.add(user)
        await session.commit()
        await session.refresh(user)

        print(
            f"Password reset for user id={user.id} "
            f"username={user.username} "
            f"email={user.email}"
        )


async def list_users_command(*, include_disabled: bool) -> None:
    maker = get_sessionmaker()
    async with maker() as session:
        statement = select(User).order_by(User.id)
        if not include_disabled:
            statement = statement.where(User.is_active.is_(True))

        result = await session.execute(statement)
        users = list(result.scalars().all())

        if not users:
            print("No users found.")
            return

        for user in users:
            status = "active" if user.is_active else "disabled"
            print(
                f"id={user.id} "
                f"username={user.username} "
                f"email={user.email} "
                f"role={user.role} "
                f"status={status}"
            )


async def find_user_by_username_or_email(
    session: AsyncSession,
    *,
    username: str,
    email: str,
) -> User | None:
    result = await session.execute(
        select(User).where(
            or_(
                User.username == username,
                User.email == email,
            )
        )
    )
    return result.scalar_one_or_none()


async def find_user(
    session: AsyncSession,
    *,
    username: str | None,
    email: str | None,
) -> User | None:
    conditions = []
    if username:
        conditions.append(User.username == normalize_username(username))
    if email:
        conditions.append(User.email == normalize_email(email))

    if not conditions:
        return None

    result = await session.execute(select(User).where(or_(*conditions)))
    return result.scalar_one_or_none()


def resolve_password(password: str | None) -> str:
    if password is None:
        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            raise SystemExit("Passwords do not match.")

    if len(password) < MIN_PASSWORD_LENGTH:
        raise SystemExit(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")

    return password


def normalize_username(username: str) -> str:
    username = username.strip()
    if not username:
        raise SystemExit("Username is required.")
    return username


def normalize_email(email: str) -> str:
    email = email.strip().lower()
    if not email:
        raise SystemExit("Email is required.")
    if "@" not in email:
        raise SystemExit("Email is invalid.")
    return email


if __name__ == "__main__":
    main()
