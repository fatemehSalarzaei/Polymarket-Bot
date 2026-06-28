from __future__ import annotations

import argparse
import asyncio
import getpass

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.models.user import User
from app.services.auth import hash_password


async def main() -> None:
    parser = argparse.ArgumentParser(description="Create the first admin user.")
    parser.add_argument("--email")
    parser.add_argument("--username")
    parser.add_argument("--password")
    args = parser.parse_args()

    settings = get_settings()
    email = args.email or settings.admin_email
    username = args.username or settings.admin_username
    password = args.password
    password_hash = settings.admin_password_hash

    if not email or not username:
        raise SystemExit("ADMIN_EMAIL and ADMIN_USERNAME are required, or pass --email and --username.")
    if not password_hash:
        password = password or getpass.getpass("Admin password: ")
        if len(password) < 10:
            raise SystemExit("Admin password must be at least 10 characters.")
        password_hash = hash_password(password)

    maker = get_sessionmaker()
    async with maker() as session:
        existing = await session.scalar(select(User.id).where((User.email == email) | (User.username == username)))
        if existing is not None:
            raise SystemExit("A user with that email or username already exists.")
        user = User(
            email=email.strip().lower(),
            username=username.strip(),
            password_hash=password_hash,
            role="admin",
            is_active=True,
        )
        session.add(user)
        await session.commit()
        print(f"Created admin user id={user.id} username={user.username}")


if __name__ == "__main__":
    asyncio.run(main())
