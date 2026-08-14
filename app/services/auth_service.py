"""Registration / login / Google-auth business logic."""

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.exceptions.errors import ConflictError, ForbiddenError, UnauthorizedError
from app.models.db import User
from app.services.google_auth_service import verify_google_token
from app.utils.security import create_access_token, hash_password, verify_password
from app.validators.user import GoogleAuthPayload, UserCreate, UserLogin


def _validate_manager_code(role: str, manager_code: Optional[str]) -> None:
    if role != "manager":
        return
    if not manager_code:
        raise ForbiddenError("Manager code required")
    if manager_code != settings.manager_code:
        raise ForbiddenError("Invalid manager code")


def _issue_token(user: User) -> str:
    return create_access_token({"sub": str(user.id), "role": user.role})


async def register_user(db: AsyncSession, payload: UserCreate) -> tuple[str, User]:
    email = payload.email.lower()
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise ConflictError("Email already registered")

    _validate_manager_code(payload.role.value, payload.manager_code)

    user = User(
        name=payload.name,
        email=email,
        password_hash=hash_password(payload.password),
        role=payload.role.value,
        created_at=datetime.utcnow(),
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        # Two registrations for the same email raced past the check above;
        # the unique index is the real guarantee, this just turns the raw
        # DB error into the same 400 a non-racing duplicate would get.
        await db.rollback()
        raise ConflictError("Email already registered")
    await db.refresh(user)

    return _issue_token(user), user


async def login_user(db: AsyncSession, payload: UserLogin) -> tuple[str, User]:
    email = payload.email.lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise UnauthorizedError("Invalid email or password")

    return _issue_token(user), user


async def google_login_or_register(
    db: AsyncSession, payload: GoogleAuthPayload
) -> tuple[str, User]:
    """Frontend sends a Google ID token; verify it and log in or register."""
    google_user = await verify_google_token(payload.id_token)
    email = google_user["email"].lower()

    result = await db.execute(select(User).where(User.email == email))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        return _issue_token(existing_user), existing_user

    _validate_manager_code(payload.role.value, payload.manager_code)

    user = User(
        name=google_user["name"],
        email=email,
        password_hash=hash_password(
            google_user["id"]
        ),  # Store Google ID as password hash
        role=payload.role.value,
        google_id=google_user["id"],
        created_at=datetime.utcnow(),
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictError("Email already registered")
    await db.refresh(user)

    return _issue_token(user), user
