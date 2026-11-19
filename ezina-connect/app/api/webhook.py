"""Meta WhatsApp webhook: verification, signed delivery, persist-then-ack, status callbacks."""
from __future__ import annotations

import hashlib
import hmac
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_container, get_processor, get_session
from app.logging_config import mask_phone
from app.models import Message
from app.schemas.whatsapp import WAStatus, WebhookPayload, normalize_message
from app.services.container import Container
from app.services.message_processor import MessageProcessor

log = logging.getLogger("ezina.webhook")
router = APIRouter()

# delivery states only move forward; 'failed' always wins (out-of-order status callbacks)
_RANK = {"queued": 0, "sent": 1, "delivered": 2, "read": 3, "failed": 4}


def verify_signature(secret: str, body: bytes, header: str | None) -> bool:
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[len("sha256="):])


@router.get("/webhook")
async def verify_webhook(
    hub_mode: str | None = Query(None, alias="hub.mode"),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(None, alias="hub.challenge"),
    c: Container = Depends(get_container),
):
    expected = c.settings.whatsapp_verify_token.get_secret_value()
    if (
        hub_mode == "subscribe"
        and expected
        and hub_verify_token
        and hmac.compare_digest(hub_verify_token.encode(), expected.encode())
    ):
        return Response(content=hub_challenge or "", media_type="text/plain")
    raise HTTPException(403, "verification failed")


@router.post("/webhook")
async def receive_webhook(
    request: Request,
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    c: Container = Depends(get_container),
    processor: MessageProcessor = Depends(get_processor),
):
    body = await request.body()
    if not verify_signature(
        c.settings.meta_app_secret.get_secret_value(), body, request.headers.get("X-Hub-Signature-256")
    ):
        log.warning("webhook signature rejected")
        raise HTTPException(401, "invalid signature")

    try:
        payload = WebhookPayload.model_validate_json(body)
    except ValidationError:
        log.warning("webhook payload did not parse")
        return {"status": "ignored"}  # 200 so Meta doesn't retry a payload we can never parse

    wa_ids: set[str] = set()
    for entry in payload.entry:
        for change in entry.changes:
            value = change.value
            names = {ct.wa_id: (ct.profile.name if ct.profile else None) for ct in value.contacts}
            for m in value.messages:
                try:
                    n = normalize_message(m, names.get(m.from_))
                except ValueError:
                    log.warning("message with invalid sender ignored")
                    continue
                if await _persist_inbound(session, n):
                    wa_ids.add(n.wa_id)
            for st in value.statuses:
                await _apply_status(session, st)

    await session.commit()  # inbound rows are durable BEFORE we acknowledge
    for wa_id in wa_ids:
        background.add_task(processor.process_farmer, wa_id)
    return {"status": "ok"}


async def _persist_inbound(session: AsyncSession, n) -> bool:
    """Insert once per WhatsApp message id. Returns False for duplicates."""
    exists = (
        await session.execute(select(Message.id).where(Message.wa_message_id == n.wa_message_id))
    ).first()
    if exists:
        log.info("duplicate message ignored", extra={"farmer": mask_phone(n.wa_id)})
        return False
    try:
        async with session.begin_nested():
            session.add(
                Message(
                    wa_id=n.wa_id, direction="INBOUND", wa_message_id=n.wa_message_id, type=n.type,
                    content=n.to_content(), status="received", processing_status="received",
                    wa_timestamp=n.wa_timestamp,
                )
            )
        return True
    except IntegrityError:  # concurrent duplicate delivery lost the race on the unique constraint
        return False


async def _apply_status(session: AsyncSession, st: WAStatus) -> None:
    row = (
        await session.execute(
            select(Message).where(Message.wa_message_id == st.id, Message.direction == "OUTBOUND")
        )
    ).scalar_one_or_none()
    if row is None:
        log.info("status for unknown message", extra={"status": st.status})
        return
    new = st.status.lower()
    if new not in _RANK or _RANK[new] <= _RANK.get(row.status, 0):
        return  # older/duplicate callback must not regress newer state
    row.status = new
    if new == "failed" and st.errors:
        e = st.errors[0]
        row.error = f"{e.code}: {e.title or e.message}"[:500]
