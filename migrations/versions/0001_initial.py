"""initial schema: users, orders, logs, newsletter

Revision ID: 0001
Revises:
Create Date: 2026-08-13

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Backs order_service.generate_tracking_id(): a DB sequence is atomic
    # under concurrent order creation, unlike a SELECT count(*) race.
    op.execute("CREATE SEQUENCE order_tracking_seq START WITH 1 INCREMENT BY 1")

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "role", sa.String(length=20), nullable=False, server_default="customer"
        ),
        sa.Column("google_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("tracking_id", sa.String(length=50), nullable=False),
        sa.Column(
            "customer_name", sa.String(length=100), nullable=False, server_default=""
        ),
        sa.Column(
            "customer_email", sa.String(length=255), nullable=False, server_default=""
        ),
        sa.Column("service_type", sa.String(length=20), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="pending"
        ),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("base_fee", sa.Float(), nullable=False),
        sa.Column("cart", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("items", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_orders_tracking_id", "orders", ["tracking_id"], unique=True)

    op.create_table(
        "logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("action", sa.String(length=255), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "newsletter",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("subscribed_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_newsletter_email", "newsletter", ["email"], unique=True)


def downgrade() -> None:
    op.drop_table("newsletter")
    op.drop_table("logs")
    op.drop_index("ix_orders_tracking_id", table_name="orders")
    op.drop_table("orders")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    op.execute("DROP SEQUENCE order_tracking_seq")
