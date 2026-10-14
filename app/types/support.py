from enum import Enum
from typing import Optional

from pydantic import BaseModel


class SupportCategory(str, Enum):
    general = "general"
    order_issue = "order_issue"
    pricing = "pricing"
    complaint = "complaint"
    pickup_delivery = "pickup_delivery"
    payment = "payment"


class SupportRequestStatus(str, Enum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"


class SupportMessageOut(BaseModel):
    id: str
    seq: int
    role: str
    kind: str
    status: str
    content: str
    error_code: Optional[str] = None
    client_msg_id: Optional[str] = None
    created_at: str


class ConversationCreatedOut(BaseModel):
    conversation_id: str
    token: str


class MessageAcceptedOut(BaseModel):
    message: SupportMessageOut
    duplicate: bool = False


class MessagesOut(BaseModel):
    messages: list[SupportMessageOut]
    stage: Optional[str]  # collecting | transcribing | thinking | None
    poll_after_ms: int


class SupportConfigOut(BaseModel):
    assistant_name: str
    ai_available: bool
    voice_input: bool
    voice_output: bool
    voice_max_seconds: int
    max_message_chars: int


class SupportRequestOut(BaseModel):
    id: str
    reference: str
    category: str
    message: str
    contact_name: str
    contact_email: Optional[str]
    contact_phone: Optional[str]
    excerpt: list[dict]
    status: str
    signed_in_customer: bool
    created_at: str
    updated_at: str
