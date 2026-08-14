"""Newsletter subscription logic."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.errors import ConflictError
from app.models.db import Newsletter
from app.validators.newsletter import NewsletterSubscribe


async def subscribe(db: AsyncSession, payload: NewsletterSubscribe) -> None:
    email = payload.email.lower()
    result = await db.execute(select(Newsletter).where(Newsletter.email == email))
    if result.scalar_one_or_none():
        raise ConflictError("Already subscribed")

    db.add(Newsletter(email=email, subscribed_at=datetime.utcnow()))
    try:
        await db.commit()
    except IntegrityError:
        # Two subscribe calls for the same email raced past the check above.
        await db.rollback()
        raise ConflictError("Already subscribed")
