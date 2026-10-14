import re
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.types.support import SupportCategory, SupportRequestStatus

# Client-generated idempotency key: a UUID or similar opaque token.
CLIENT_MSG_ID_PATTERN = r"^[A-Za-z0-9_-]{8,64}$"
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(value: str) -> str:
    return _CONTROL_CHARS.sub("", value).strip()


class SupportMessageCreate(BaseModel):
    client_msg_id: str = Field(..., pattern=CLIENT_MSG_ID_PATTERN)
    # Upper bound is enforced again against settings in the route; this is
    # the hard ceiling for the request body.
    text: str = Field(..., min_length=1, max_length=4000)

    @field_validator("text")
    @classmethod
    def _clean(cls, v: str) -> str:
        v = clean_text(v)
        if not v:
            raise ValueError("Message cannot be empty")
        return v


class EscalationCreate(BaseModel):
    category: SupportCategory = SupportCategory.general
    message: str = Field(..., min_length=3, max_length=1000)
    contact_name: str = Field(..., min_length=2, max_length=100)
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = Field(None, max_length=30)
    include_chat_excerpt: bool = True

    @field_validator("message", "contact_name")
    @classmethod
    def _clean(cls, v: str) -> str:
        return clean_text(v)

    @field_validator("contact_phone")
    @classmethod
    def _phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        v = v.strip()
        if not re.fullmatch(r"\+?[0-9 ()-]{7,30}", v):
            raise ValueError("Enter a valid phone number")
        return v

    @model_validator(mode="after")
    def _needs_contact(self) -> "EscalationCreate":
        if not self.contact_email and not self.contact_phone:
            raise ValueError("Add an email address or phone number so we can reach you")
        return self


class SupportRequestUpdate(BaseModel):
    status: SupportRequestStatus
