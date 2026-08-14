from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from app.types.user import Role


class UserCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6)
    role: Role = Role.customer
    manager_code: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class GoogleAuthPayload(BaseModel):
    id_token: str
    role: Role = Role.customer
    manager_code: Optional[str] = None
