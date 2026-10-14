"""Human hand-off: record support requests and let managers work through them."""

import secrets
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.errors import NotFoundError
from app.models.db import SupportConversation, SupportMessage, SupportRequest, User
from app.services.support_conversation_service import add_system_message
from app.utils import metrics
from app.validators.support import EscalationCreate, SupportRequestUpdate

EXCERPT_MESSAGES = 6
EXCERPT_CHARS = 300


async def _excerpt(db: AsyncSession, conv_id: uuid.UUID) -> list[dict]:
    """Last few customer messages, trimmed. Enough context for staff, not the
    whole chat history."""
    result = await db.execute(
        select(SupportMessage)
        .where(
            SupportMessage.conversation_id == conv_id,
            SupportMessage.role == "customer",
            SupportMessage.status == "ready",
        )
        .order_by(SupportMessage.seq.desc())
        .limit(EXCERPT_MESSAGES)
    )
    rows = list(reversed(result.scalars().all()))
    return [
        {
            "kind": m.kind,
            "text": m.content[:EXCERPT_CHARS],
            "at": m.created_at.isoformat(),
        }
        for m in rows
    ]


def _new_reference() -> str:
    return f"SR-{secrets.token_hex(4).upper()}"


async def create_support_request(
    db: AsyncSession,
    conv: SupportConversation,
    payload: EscalationCreate,
    user: User | None,
    now: datetime,
) -> SupportRequest:
    excerpt = await _excerpt(db, conv.id) if payload.include_chat_excerpt else []
    for _ in range(3):
        request = SupportRequest(
            reference=_new_reference(),
            conversation_id=conv.id,
            user_id=user.id if user else conv.user_id,
            category=payload.category.value,
            message=payload.message,
            contact_name=payload.contact_name,
            contact_email=payload.contact_email,
            contact_phone=payload.contact_phone,
            excerpt=excerpt,
            status="open",
            created_at=now,
            updated_at=now,
        )
        db.add(request)
        await add_system_message(
            db,
            conv.id,
            f"Support request {request.reference} was recorded for the Gpron team "
            "(staff have not been notified automatically; they review requests "
            "during opening hours).",
            now,
        )
        try:
            await db.commit()
        except IntegrityError:
            # Reference collision (vanishingly rare): roll back and retry.
            await db.rollback()
            continue
        await db.refresh(request)
        metrics.support_escalations_total.labels(category=request.category).inc()
        return request
    raise RuntimeError("Could not allocate a support request reference")


async def list_support_requests(
    db: AsyncSession, status: str | None, limit: int = 200
) -> list[SupportRequest]:
    query = (
        select(SupportRequest).order_by(SupportRequest.created_at.desc()).limit(limit)
    )
    if status:
        query = query.where(SupportRequest.status == status)
    result = await db.execute(query)
    return list(result.scalars().all())


async def update_support_request(
    db: AsyncSession, request_id: str, payload: SupportRequestUpdate, now: datetime
) -> SupportRequest:
    try:
        req_uuid = uuid.UUID(request_id)
    except ValueError:
        raise NotFoundError("Support request not found")
    request = await db.get(SupportRequest, req_uuid)
    if request is None:
        raise NotFoundError("Support request not found")
    request.status = payload.status.value
    request.updated_at = now
    await db.commit()
    await db.refresh(request)
    return request
