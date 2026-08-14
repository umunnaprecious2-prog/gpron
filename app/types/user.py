from enum import Enum

from pydantic import BaseModel


class Role(str, Enum):
    customer = "customer"
    manager = "manager"


class UserOut(BaseModel):
    id: str
    name: str
    email: str
    role: str
    created_at: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
