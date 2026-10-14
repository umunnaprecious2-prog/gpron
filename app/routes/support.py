"""Customer support agent API (public chat + manager hand-off queue).

Conversation endpoints authenticate with the per-conversation token returned
at creation, sent as the X-Support-Token header.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.exceptions.errors import (
    NotFoundError,
    ServiceUnavailableError,
    ValidationFailedError,
)
from app.middlewares.auth_middleware import get_optional_user, require_manager
from app.models.db import SupportMessage, SupportRequest, User
from app.services import support_conversation_service as conversations
from app.services.speech_service import SpeechError
from app.services.support_escalation_service import (
    create_support_request,
    list_support_requests,
    update_support_request,
)
from app.services.support_voice_service import (
    transcribe_and_store,
    validate_audio_upload,
)
from app.services.support_worker import SupportRuntime
from app.types.support import (
    ConversationCreatedOut,
    MessageAcceptedOut,
    MessagesOut,
    SupportConfigOut,
    SupportMessageOut,
    SupportRequestOut,
    SupportRequestStatus,
)
from app.utils import metrics
from app.utils.rate_limit import client_ip
from app.validators.support import (
    CLIENT_MSG_ID_PATTERN,
    EscalationCreate,
    SupportMessageCreate,
    SupportRequestUpdate,
)

router = APIRouter(prefix="/support", tags=["support"])

ASSISTANT_NAME = "Ada"
POLL_ACTIVE_MS = 1000


def get_runtime(request: Request) -> SupportRuntime:
    runtime = getattr(request.app.state, "support", None)
    if runtime is None:
        raise ServiceUnavailableError("Support chat is not available right now.")
    return runtime


def format_message(msg: SupportMessage) -> SupportMessageOut:
    return SupportMessageOut(
        id=str(msg.id),
        seq=msg.seq,
        role=msg.role,
        kind=msg.kind,
        status=msg.status,
        content=msg.content,
        error_code=msg.error_code,
        client_msg_id=msg.client_msg_id,
        created_at=msg.created_at.isoformat(),
    )


def format_request(req: SupportRequest) -> SupportRequestOut:
    return SupportRequestOut(
        id=str(req.id),
        reference=req.reference,
        category=req.category,
        message=req.message,
        contact_name=req.contact_name,
        contact_email=req.contact_email,
        contact_phone=req.contact_phone,
        excerpt=req.excerpt or [],
        status=req.status,
        signed_in_customer=req.user_id is not None,
        created_at=req.created_at.isoformat(),
        updated_at=req.updated_at.isoformat(),
    )


@router.get("/config", response_model=SupportConfigOut)
async def support_config(runtime: SupportRuntime = Depends(get_runtime)):
    s = runtime.settings
    return SupportConfigOut(
        assistant_name=ASSISTANT_NAME,
        ai_available=runtime.ai_available,
        voice_input=runtime.speech is not None,
        voice_output=runtime.voice_output_available,
        voice_max_seconds=s.voice_max_seconds,
        max_message_chars=s.support_max_message_chars,
    )


@router.post("/conversations", response_model=ConversationCreatedOut, status_code=201)
async def create_conversation(
    request: Request,
    runtime: SupportRuntime = Depends(get_runtime),
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    runtime.limiters.conversations_per_ip.check(client_ip(request))
    conv, token = await conversations.create_conversation(db, user, datetime.utcnow())
    return ConversationCreatedOut(conversation_id=str(conv.id), token=token)


@router.get("/conversations/{conversation_id}/messages", response_model=MessagesOut)
async def get_messages(
    conversation_id: str,
    after_seq: int = Query(0, ge=0),
    x_support_token: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    conv = await conversations.get_authorized_conversation(
        db, conversation_id, x_support_token
    )
    messages = await conversations.list_messages(db, conv.id, after_seq)
    stage = await conversations.conversation_stage(db, conv, datetime.utcnow())
    return MessagesOut(
        messages=[format_message(m) for m in messages],
        stage=stage,
        poll_after_ms=POLL_ACTIVE_MS if stage else 0,
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageAcceptedOut,
    status_code=202,
)
async def send_message(
    conversation_id: str,
    payload: SupportMessageCreate,
    request: Request,
    runtime: SupportRuntime = Depends(get_runtime),
    x_support_token: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    runtime.limiters.messages_per_ip.check(client_ip(request))
    conv = await conversations.get_authorized_conversation(
        db, conversation_id, x_support_token
    )
    runtime.limiters.messages_per_conversation.check(str(conv.id))
    if len(payload.text) > runtime.settings.support_max_message_chars:
        raise ValidationFailedError(
            f"Messages can be up to {runtime.settings.support_max_message_chars} characters."
        )
    result = await conversations.add_customer_message(
        db,
        conv,
        kind="text",
        content=payload.text,
        status="ready",
        client_msg_id=payload.client_msg_id,
        now=datetime.utcnow(),
        settings=runtime.settings,
    )
    if result.created and runtime.worker:
        runtime.worker.notify_new_message(conv.id)
    return MessageAcceptedOut(
        message=format_message(result.message), duplicate=not result.created
    )


@router.post(
    "/conversations/{conversation_id}/voice",
    response_model=MessageAcceptedOut,
    status_code=202,
)
async def send_voice_note(
    conversation_id: str,
    request: Request,
    file: UploadFile = File(...),
    client_msg_id: str = Form(..., pattern=CLIENT_MSG_ID_PATTERN),
    runtime: SupportRuntime = Depends(get_runtime),
    x_support_token: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    conv = await conversations.get_authorized_conversation(
        db, conversation_id, x_support_token
    )
    if runtime.speech is None:
        raise ServiceUnavailableError(
            "Voice notes aren't available right now. Please type your message."
        )
    runtime.limiters.messages_per_ip.check(client_ip(request))
    runtime.limiters.voice_per_conversation.check(str(conv.id))

    # Read at most limit+1 bytes: enough to detect oversize without buffering
    # an arbitrarily large upload.
    data = await file.read(runtime.settings.voice_max_upload_bytes + 1)
    await file.close()
    audio = validate_audio_upload(data, file.content_type, runtime.settings)

    result = await conversations.add_customer_message(
        db,
        conv,
        kind="voice",
        content="",
        status="transcribing",
        client_msg_id=client_msg_id,
        now=datetime.utcnow(),
        settings=runtime.settings,
    )
    if result.created:
        job = transcribe_and_store(
            runtime.session_factory,
            runtime.speech,
            result.message.id,
            audio,
            runtime.settings,
        )
        if runtime.worker:
            runtime.worker.submit(job)
            runtime.worker.notify_new_message(conv.id)
        else:
            await job
    return MessageAcceptedOut(
        message=format_message(result.message), duplicate=not result.created
    )


@router.get("/conversations/{conversation_id}/messages/{message_id}/audio")
async def get_message_audio(
    conversation_id: str,
    message_id: str,
    runtime: SupportRuntime = Depends(get_runtime),
    x_support_token: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    conv = await conversations.get_authorized_conversation(
        db, conversation_id, x_support_token
    )
    msg = await conversations.get_message(db, conv.id, message_id)
    if msg.role != "assistant" or not msg.content:
        raise NotFoundError("No audio for this message")
    if runtime.speech is None or not runtime.voice_output_available:
        raise ServiceUnavailableError("Audio playback isn't available right now.")
    runtime.limiters.tts_per_conversation.check(str(conv.id))
    try:
        audio = await runtime.speech.synthesize(
            msg.content[: runtime.settings.tts_max_chars]
        )
    except SpeechError as exc:
        metrics.support_tts_total.labels(outcome=exc.reason).inc()
        raise ServiceUnavailableError(
            "Couldn't generate audio right now. Please try again."
        )
    metrics.support_tts_total.labels(outcome="ok").inc()
    # Not cached server-side; the browser keeps it for this session only.
    return Response(
        content=audio.data,
        media_type=audio.media_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.post(
    "/conversations/{conversation_id}/escalate",
    response_model=SupportRequestOut,
    status_code=201,
)
async def escalate(
    conversation_id: str,
    payload: EscalationCreate,
    request: Request,
    runtime: SupportRuntime = Depends(get_runtime),
    user: Optional[User] = Depends(get_optional_user),
    x_support_token: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    runtime.limiters.escalations_per_ip.check(client_ip(request))
    conv = await conversations.get_authorized_conversation(
        db, conversation_id, x_support_token
    )
    req = await create_support_request(db, conv, payload, user, datetime.utcnow())
    return format_request(req)


@router.get("/requests", response_model=list[SupportRequestOut])
async def get_support_requests(
    status: Optional[SupportRequestStatus] = None,
    current_user: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    requests = await list_support_requests(db, status.value if status else None)
    return [format_request(r) for r in requests]


@router.patch("/requests/{request_id}", response_model=SupportRequestOut)
async def patch_support_request(
    request_id: str,
    payload: SupportRequestUpdate,
    current_user: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    req = await update_support_request(db, request_id, payload, datetime.utcnow())
    return format_request(req)
