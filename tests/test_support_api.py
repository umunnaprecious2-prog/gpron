"""HTTP-level tests: access control, validation, voice uploads, escalation."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.test_orders import get_token

WEBM_MAGIC = b"\x1a\x45\xdf\xa3" + b"\x00" * 2000
OGG_MAGIC = b"OggS" + b"\x00" * 2000


def client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def start_chat(c: AsyncClient, headers: dict | None = None) -> tuple[str, dict]:
    res = await c.post("/support/conversations", headers=headers or {})
    assert res.status_code == 201
    body = res.json()
    return body["conversation_id"], {"X-Support-Token": body["token"]}


def msg(text: str, key: str | None = None) -> dict:
    return {"client_msg_id": key or uuid.uuid4().hex, "text": text}


async def test_config_reports_capabilities(support_runtime):
    async with client() as c:
        res = await c.get("/support/config")
    assert res.status_code == 200
    body = res.json()
    assert body["ai_available"] is True
    assert body["voice_input"] is True and body["voice_output"] is True
    assert "openai_api_key" not in res.text and "test-key" not in res.text


async def test_chat_unavailable_without_runtime():
    app.state.support = None
    async with client() as c:
        res = await c.post("/support/conversations")
    assert res.status_code == 503


async def test_send_and_poll_messages(support_runtime, clock):
    async with client() as c:
        conv_id, auth = await start_chat(c)
        res = await c.post(
            f"/support/conversations/{conv_id}/messages",
            json=msg("Hello"),
            headers=auth,
        )
        assert res.status_code == 202
        res = await c.get(f"/support/conversations/{conv_id}/messages", headers=auth)
    body = res.json()
    assert [m["content"] for m in body["messages"]] == ["Hello"]
    assert body["stage"] == "collecting" and body["poll_after_ms"] > 0


async def test_api_retry_with_same_client_id_is_idempotent(support_runtime):
    async with client() as c:
        conv_id, auth = await start_chat(c)
        url = f"/support/conversations/{conv_id}/messages"
        first = await c.post(url, json=msg("hi", "same-key-0001"), headers=auth)
        second = await c.post(url, json=msg("hi", "same-key-0001"), headers=auth)
        listing = await c.get(url, headers=auth)
    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    assert first.json()["message"]["id"] == second.json()["message"]["id"]
    assert len(listing.json()["messages"]) == 1


# 15 -------------------------------------------------------------------------
async def test_conversations_are_isolated_between_customers(support_runtime):
    async with client() as c:
        conv_a, auth_a = await start_chat(c)
        conv_b, auth_b = await start_chat(c)
        await c.post(
            f"/support/conversations/{conv_a}/messages",
            json=msg("my private question"),
            headers=auth_a,
        )
        # B's token cannot read or write A's conversation.
        read = await c.get(f"/support/conversations/{conv_a}/messages", headers=auth_b)
        write = await c.post(
            f"/support/conversations/{conv_a}/messages", json=msg("x"), headers=auth_b
        )
        no_token = await c.get(f"/support/conversations/{conv_a}/messages")
        bogus_id = await c.get(
            "/support/conversations/not-a-uuid/messages", headers=auth_a
        )
    for res in (read, write, no_token, bogus_id):
        assert res.status_code == 404
    assert "private" not in read.text


@pytest.mark.parametrize(
    "payload",
    [
        {"client_msg_id": "valid-key-01", "text": ""},
        {"client_msg_id": "valid-key-01", "text": "   \x00  "},
        {"client_msg_id": "bad key!", "text": "hi"},
        {"client_msg_id": "valid-key-01", "text": "x" * 4001},
        {"text": "missing id"},
    ],
)
async def test_invalid_message_payloads_rejected(support_runtime, payload):
    async with client() as c:
        conv_id, auth = await start_chat(c)
        res = await c.post(
            f"/support/conversations/{conv_id}/messages", json=payload, headers=auth
        )
    assert res.status_code == 422


async def test_message_over_configured_length_rejected(support_runtime):
    async with client() as c:
        conv_id, auth = await start_chat(c)
        res = await c.post(
            f"/support/conversations/{conv_id}/messages",
            json=msg("x" * 1001),
            headers=auth,
        )
    assert res.status_code == 422


async def test_message_rate_limit(support_runtime):
    async with client() as c:
        conv_id, auth = await start_chat(c)
        codes = [
            (
                await c.post(
                    f"/support/conversations/{conv_id}/messages",
                    json=msg(f"m{i}"),
                    headers=auth,
                )
            ).status_code
            for i in range(22)
        ]
    assert codes[:20] == [202] * 20
    assert codes[-1] == 429


# 12 / 13 ---------------------------------------------------------------------
async def test_voice_note_is_transcribed_into_conversation(
    support_runtime, fake_speech
):
    fake_speech.transcript = "I need my suit by Friday"
    async with client() as c:
        conv_id, auth = await start_chat(c)
        res = await c.post(
            f"/support/conversations/{conv_id}/voice",
            files={"file": ("v.webm", WEBM_MAGIC, "audio/webm;codecs=opus")},
            data={"client_msg_id": uuid.uuid4().hex},
            headers=auth,
        )
        assert res.status_code == 202
        assert res.json()["message"]["status"] == "transcribing"
        listing = await c.get(
            f"/support/conversations/{conv_id}/messages", headers=auth
        )
    voice = listing.json()["messages"][0]
    assert voice["kind"] == "voice" and voice["status"] == "ready"
    assert voice["content"] == "I need my suit by Friday"


async def test_voice_transcription_failure_is_reported(support_runtime, fake_speech):
    fake_speech.fail_with = "timeout"
    async with client() as c:
        conv_id, auth = await start_chat(c)
        await c.post(
            f"/support/conversations/{conv_id}/voice",
            files={"file": ("v.ogg", OGG_MAGIC, "audio/ogg")},
            data={"client_msg_id": uuid.uuid4().hex},
            headers=auth,
        )
        listing = await c.get(
            f"/support/conversations/{conv_id}/messages", headers=auth
        )
    voice = listing.json()["messages"][0]
    assert voice["status"] == "failed" and voice["error_code"] == "timeout"


@pytest.mark.parametrize(
    "filename,data,content_type,expected",
    [
        ("v.txt", b"hello" * 400, "text/plain", 415),  # wrong type
        ("v.webm", b"<script>" * 300, "audio/webm", 415),  # not really audio
        ("v.exe", b"MZ" + b"\x00" * 3000, "audio/mpeg", 415),  # disguised binary
        ("v.webm", b"\x1a\x45\xdf\xa3", "audio/webm", 422),  # too short
    ],
)
async def test_invalid_audio_rejected(
    support_runtime, filename, data, content_type, expected
):
    async with client() as c:
        conv_id, auth = await start_chat(c)
        res = await c.post(
            f"/support/conversations/{conv_id}/voice",
            files={"file": (filename, data, content_type)},
            data={"client_msg_id": uuid.uuid4().hex},
            headers=auth,
        )
        listing = await c.get(
            f"/support/conversations/{conv_id}/messages", headers=auth
        )
    assert res.status_code == expected
    assert listing.json()["messages"] == []  # nothing persisted


async def test_oversized_audio_rejected(support_runtime):
    too_big = b"\x1a\x45\xdf\xa3" + b"\x00" * (
        support_runtime.settings.voice_max_upload_bytes + 10
    )
    async with client() as c:
        conv_id, auth = await start_chat(c)
        res = await c.post(
            f"/support/conversations/{conv_id}/voice",
            files={"file": ("v.webm", too_big, "audio/webm")},
            data={"client_msg_id": uuid.uuid4().hex},
            headers=auth,
        )
    assert res.status_code == 413


async def test_voice_disabled_without_speech_provider(support_runtime):
    support_runtime.speech = None
    async with client() as c:
        conv_id, auth = await start_chat(c)
        res = await c.post(
            f"/support/conversations/{conv_id}/voice",
            files={"file": ("v.webm", WEBM_MAGIC, "audio/webm")},
            data={"client_msg_id": uuid.uuid4().hex},
            headers=auth,
        )
        config = await c.get("/support/config")
    assert res.status_code == 503
    assert "type your message" in res.json()["detail"]
    assert config.json()["voice_input"] is False


async def test_reply_audio_playback(support_runtime, clock):
    async with client() as c:
        conv_id, auth = await start_chat(c)
        await c.post(
            f"/support/conversations/{conv_id}/messages", json=msg("hi"), headers=auth
        )
        clock.advance(15)  # route stamps real time, slightly ahead of the fake clock
        assert (
            await support_runtime.processor.process(uuid.UUID(conv_id)) == "delivered"
        )
        listing = (
            await c.get(f"/support/conversations/{conv_id}/messages", headers=auth)
        ).json()
        customer_msg, reply = listing["messages"]
        audio = await c.get(
            f"/support/conversations/{conv_id}/messages/{reply['id']}/audio",
            headers=auth,
        )
        not_assistant = await c.get(
            f"/support/conversations/{conv_id}/messages/{customer_msg['id']}/audio",
            headers=auth,
        )
    assert listing["stage"] is None and listing["poll_after_ms"] == 0
    assert audio.status_code == 200 and audio.headers["content-type"] == "audio/mpeg"
    assert not_assistant.status_code == 404


# 16 -------------------------------------------------------------------------
async def test_escalation_is_persisted_and_visible_to_managers(support_runtime):
    async with client() as c:
        conv_id, auth = await start_chat(c)
        await c.post(
            f"/support/conversations/{conv_id}/messages",
            json=msg("My shirt came back damaged"),
            headers=auth,
        )
        res = await c.post(
            f"/support/conversations/{conv_id}/escalate",
            json={
                "category": "complaint",
                "message": "Damaged shirt on order GPRON-2026-0001",
                "contact_name": "Ada Customer",
                "contact_phone": "+234 801 234 5678",
            },
            headers=auth,
        )
        assert res.status_code == 201
        ticket = res.json()
        assert ticket["reference"].startswith("SR-")
        assert ticket["excerpt"][0]["text"] == "My shirt came back damaged"

        listing = await c.get(
            f"/support/conversations/{conv_id}/messages", headers=auth
        )
        note = listing.json()["messages"][-1]
        assert note["role"] == "system" and ticket["reference"] in note["content"]
        assert "not been notified" in note["content"]

        mgr = await get_token(c, "mgr_support_queue@example.com", "pass1234", "manager")
        cust = await get_token(c, "cust_support_queue@example.com", "pass1234")
        queue = await c.get(
            "/support/requests?status=open",
            headers={"Authorization": f"Bearer {mgr}"},
        )
        forbidden = await c.get(
            "/support/requests", headers={"Authorization": f"Bearer {cust}"}
        )
        anonymous = await c.get("/support/requests")
        update = await c.patch(
            f"/support/requests/{ticket['id']}",
            json={"status": "resolved"},
            headers={"Authorization": f"Bearer {mgr}"},
        )
    assert ticket["reference"] in [t["reference"] for t in queue.json()]
    assert forbidden.status_code == 403
    assert anonymous.status_code in (401, 403)
    assert update.json()["status"] == "resolved"


@pytest.mark.parametrize(
    "payload",
    [
        {"message": "help", "contact_name": "Ada"},  # no contact method
        {"message": "help", "contact_name": "Ada", "contact_email": "not-an-email"},
        {"message": "help", "contact_name": "Ada", "contact_phone": "call me"},
        {
            "message": "help",
            "contact_name": "Ada",
            "contact_phone": "080",
            "category": "x",
        },
    ],
)
async def test_escalation_validation(support_runtime, payload):
    async with client() as c:
        conv_id, auth = await start_chat(c)
        res = await c.post(
            f"/support/conversations/{conv_id}/escalate", json=payload, headers=auth
        )
    assert res.status_code == 422


async def test_escalation_requires_conversation_token(support_runtime):
    async with client() as c:
        conv_id, _ = await start_chat(c)
        res = await c.post(
            f"/support/conversations/{conv_id}/escalate",
            json={
                "message": "help",
                "contact_name": "Ada",
                "contact_phone": "08012345678",
            },
        )
    assert res.status_code == 404


async def test_expired_login_token_falls_back_to_anonymous_chat(support_runtime):
    async with client() as c:
        res = await c.post(
            "/support/conversations",
            headers={"Authorization": "Bearer expired.bad.jwt"},
        )
    assert res.status_code == 201


async def test_oversized_json_body_rejected_early(support_runtime):
    async with client() as c:
        conv_id, auth = await start_chat(c)
        res = await c.post(
            f"/support/conversations/{conv_id}/messages",
            content=b'{"text":"' + b"x" * 70_000 + b'"}',
            headers={**auth, "Content-Type": "application/json"},
        )
    assert res.status_code == 413


async def test_catalog_endpoint(support_runtime):
    async with client() as c:
        res = await c.get("/catalog")
    body = res.json()
    assert body["base_fee"] == {"normal": 500.0, "express": 900.0}
    assert body["express_multiplier"] == 1.6
    assert {"id": "shirt", "price": 150}.items() <= body["items"][0].items()


async def test_metrics_endpoint_requires_token(monkeypatch):
    from app.config import settings

    async with client() as c:
        monkeypatch.setattr(settings, "metrics_token", "")
        disabled = await c.get("/metrics")
        monkeypatch.setattr(settings, "metrics_token", "scrape-secret")
        wrong = await c.get("/metrics", headers={"Authorization": "Bearer nope"})
        ok = await c.get("/metrics", headers={"Authorization": "Bearer scrape-secret"})
    assert disabled.status_code == 404 and wrong.status_code == 404
    assert ok.status_code == 200 and "gpron_support_messages_total" in ok.text
