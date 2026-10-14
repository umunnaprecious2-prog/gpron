"""SQLAlchemy ORM models. This is the single source of truth for the Postgres schema."""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Sequence,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Backs order_service.generate_tracking_id(). Declared on the metadata (not
# only in migration 0001) so Base.metadata.create_all() in tests creates it too.
order_tracking_seq = Sequence(
    "order_tracking_seq", start=1, increment=1, metadata=Base.metadata
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="customer")
    google_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    tracking_id: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    customer_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    customer_email: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    service_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    price: Mapped[float] = mapped_column(Float, nullable=False)
    base_fee: Mapped[float] = mapped_column(Float, nullable=False)
    cart: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    items: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Log(Base):
    __tablename__ = "logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Newsletter(Base):
    __tablename__ = "newsletter"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    subscribed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SupportConversation(Base):
    """One customer support chat. Also holds the batching state machine.

    Sequence counters (all per conversation):
      last_seq             highest seq handed to any message (customer/assistant/system)
      customer_seq         seq of the newest customer message
      replied_through_seq  newest customer seq already covered by an assistant reply
    A conversation is waiting for a reply while customer_seq > replied_through_seq.

    claim_id/claim_expires_at is a lease: a worker sets it with a compare-and-set
    UPDATE before generating, and must still hold it when delivering. Expired
    leases can be taken over, so a crashed worker never blocks a conversation.
    """

    __tablename__ = "support_conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    last_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    customer_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    replied_through_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    batch_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_customer_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    claim_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    stale_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )


class SupportMessage(Base):
    __tablename__ = "support_messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "seq", name="uq_support_messages_seq"),
        # Network retries resend the same client_msg_id; this makes them no-ops.
        UniqueConstraint(
            "conversation_id", "client_msg_id", name="uq_support_messages_client_id"
        ),
        # At most one assistant reply per customer batch, even across workers.
        UniqueConstraint(
            "conversation_id", "reply_to_seq", name="uq_support_messages_reply_to"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("support_conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # customer|assistant|system
    kind: Mapped[str] = mapped_column(String(10), nullable=False, default="text")
    # ready | transcribing | failed (customer); ready | fallback (assistant)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ready")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    client_msg_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reply_to_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SupportRequest(Base):
    """A hand-off to human staff. Stores only a short excerpt, not the full chat."""

    __tablename__ = "support_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    reference: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("support_conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    contact_name: Mapped[str] = mapped_column(String(100), nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    excerpt: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="open", index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
