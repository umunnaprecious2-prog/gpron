from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.db import User
from app.services.auth_service import (
    google_login_or_register,
    login_user,
    register_user,
)
from app.types.user import TokenResponse, UserOut
from app.validators.user import GoogleAuthPayload, UserCreate, UserLogin

router = APIRouter(prefix="/auth", tags=["auth"])


def format_user(user: User) -> UserOut:
    return UserOut(
        id=str(user.id),
        name=user.name,
        email=user.email,
        role=user.role,
        created_at=user.created_at.isoformat(),
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    token, user = await register_user(db, payload)
    return TokenResponse(access_token=token, user=format_user(user))


@router.post("/login", response_model=TokenResponse)
async def login(payload: UserLogin, db: AsyncSession = Depends(get_db)):
    token, user = await login_user(db, payload)
    return TokenResponse(access_token=token, user=format_user(user))


@router.post("/google", response_model=TokenResponse, status_code=201)
async def google_auth(payload: GoogleAuthPayload, db: AsyncSession = Depends(get_db)):
    """Frontend sends a Google ID token; backend verifies and logs in / registers."""
    token, user = await google_login_or_register(db, payload)
    return TokenResponse(access_token=token, user=format_user(user))
