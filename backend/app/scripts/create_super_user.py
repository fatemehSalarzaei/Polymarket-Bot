from __future__ import annotations

import asyncio

from app.scripts.create_admin_user import main


if __name__ == "__main__":
    asyncio.run(main(default_role="super_user"))
