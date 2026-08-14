"""Create the two verified dev/test accounts against whichever DATABASE_URL
is active (local Docker Postgres or a hosted provider).

Run with:
    python -m app.scripts.seed_dev_data
or, inside Docker:
    docker compose exec backend python -m app.scripts.seed_dev_data
"""

import asyncio
from datetime import datetime

from sqlalchemy import select

from app.database import SessionLocal
from app.models.db import User
from app.utils.security import hash_password

SEED_ACCOUNTS = [
    {
        "name": "Test Customer",
        "email": "customer@gpron.com",
        "password": "customer123",
        "role": "customer",
    },
    {
        "name": "Test Manager",
        "email": "manager@gpron.com",
        "password": "manager123",
        "role": "manager",
    },
]


async def seed() -> None:
    async with SessionLocal() as db:
        for account in SEED_ACCOUNTS:
            existing = await db.execute(
                select(User).where(User.email == account["email"])
            )
            if existing.scalar_one_or_none():
                print(f"Skipping {account['email']} (already exists)")
                continue

            db.add(
                User(
                    name=account["name"],
                    email=account["email"],
                    password_hash=hash_password(account["password"]),
                    role=account["role"],
                    created_at=datetime.utcnow(),
                )
            )
            print(f"Created {account['role']} account: {account['email']}")

        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed())
