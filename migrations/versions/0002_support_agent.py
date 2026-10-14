"""support agent: conversations, messages, human support requests

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-14

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "support_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("last_seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("customer_seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "replied_through_seq", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("batch_started_at", sa.DateTime(), nullable=True),
        sa.Column("last_customer_at", sa.DateTime(), nullable=True),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("claim_id", sa.String(length=36), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(), nullable=True),
        sa.Column("stale_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_support_conversations_due_at", "support_conversations", ["due_at"]
    )
    op.create_index(
        "ix_support_conversations_updated_at", "support_conversations", ["updated_at"]
    )

    op.create_table(
        "support_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("support_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False, server_default="text"),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="ready"
        ),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("client_msg_id", sa.String(length=64), nullable=True),
        sa.Column("reply_to_seq", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("conversation_id", "seq", name="uq_support_messages_seq"),
        sa.UniqueConstraint(
            "conversation_id", "client_msg_id", name="uq_support_messages_client_id"
        ),
        sa.UniqueConstraint(
            "conversation_id", "reply_to_seq", name="uq_support_messages_reply_to"
        ),
    )

    op.create_table(
        "support_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("reference", sa.String(length=20), nullable=False),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("support_conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("contact_name", sa.String(length=100), nullable=False),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("contact_phone", sa.String(length=30), nullable=True),
        sa.Column("excerpt", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="open"
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("reference"),
    )
    op.create_index("ix_support_requests_status", "support_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_support_requests_status", table_name="support_requests")
    op.drop_table("support_requests")
    op.drop_table("support_messages")
    op.drop_index(
        "ix_support_conversations_updated_at", table_name="support_conversations"
    )
    op.drop_index("ix_support_conversations_due_at", table_name="support_conversations")
    op.drop_table("support_conversations")
