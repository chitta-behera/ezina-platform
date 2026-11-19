"""Durable, ordered, per-farmer message processing.

Pipeline per farmer:  lock -> oldest pending inbound message -> ConversationService (state + outbox rows)
                      -> COMMIT -> flush outbox to WhatsApp -> repeat until nothing is pending.

* Ordering: pending messages are taken oldest-first by WhatsApp timestamp, one at a time, under a per-farmer lock
  (in-process asyncio lock + PostgreSQL pg_advisory_xact_lock so multiple replicas agree).
* Durability: the inbound row is committed before the webhook returns 200; `recover()` re-queues anything left in
  'received'/'processing' after a crash/restart.
* Replies are outbox rows committed atomically with the state change, so a crash can't lose or double-send them.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from sqlalchemy import select

from app.database import advisory_xact_lock, utcnow
from app.enums import DeliveryStatus, ProcessingStatus
from app.logging_config import mask_phone
from app.models import Message
from app.services.container import Container
from app.services.conversation_service import ConversationService
from app.workflows import messages as M

log = logging.getLogger("ezina.processor")


class MessageProcessor:
    def __init__(self, c: Container):
        self.c = c
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._tasks: set[asyncio.Task] = set()

    # -- scheduling
    def schedule(self, wa_id: str) -> None:
        task = asyncio.create_task(self.process_farmer(wa_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def drain(self) -> None:
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def recover(self) -> int:
        """On startup: re-process messages left in received/processing; flush any queued outbound rows."""
        async with self.c.db.sessionmaker() as s:
            inbound = (
                await s.execute(
                    select(Message.wa_id)
                    .where(
                        Message.direction == "INBOUND",
                        Message.processing_status.in_([ProcessingStatus.RECEIVED, ProcessingStatus.PROCESSING]),
                    )
                    .distinct()
                )
            ).scalars().all()
            queued = (
                await s.execute(
                    select(Message.wa_id).where(Message.direction == "OUTBOUND", Message.status == DeliveryStatus.QUEUED).distinct()
                )
            ).scalars().all()
        farmers = set(inbound) | set(queued)
        for wa_id in farmers:
            self.schedule(wa_id)
        log.info("recovery scheduled", extra={"farmers": len(farmers)})
        return len(farmers)

    # -- main loop
    async def process_farmer(self, wa_id: str) -> None:
        async with self._locks[wa_id]:
            try:
                while True:
                    handled = await self._process_next(wa_id)
                    await self._flush_outbox(wa_id)
                    if not handled:
                        break
            except Exception:  # never let a background task die silently
                log.exception("process_farmer crashed", extra={"farmer": mask_phone(wa_id)})

    async def _process_next(self, wa_id: str) -> bool:
        msg_id = None
        try:
            async with self.c.db.sessionmaker() as session, session.begin():
                await advisory_xact_lock(session, f"farmer:{wa_id}")
                msg = (
                    await session.execute(
                        select(Message)
                        .where(
                            Message.wa_id == wa_id,
                            Message.direction == "INBOUND",
                            Message.processing_status.in_([ProcessingStatus.RECEIVED, ProcessingStatus.PROCESSING]),
                        )
                        .order_by(Message.wa_timestamp, Message.created_at)
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if msg is None:
                    return False
                msg_id = msg.id
                if msg.attempts >= self.c.settings.max_processing_attempts:
                    msg.processing_status, msg.error = ProcessingStatus.FAILED, "max attempts exceeded"
                    return True
                msg.processing_status = ProcessingStatus.PROCESSING
                msg.attempts += 1
                await ConversationService(session, self.c).process(msg)
                msg.processing_status, msg.processed_at, msg.error = ProcessingStatus.PROCESSED, utcnow(), None
            return True
        except Exception as e:
            log.exception("message processing failed", extra={"farmer": mask_phone(wa_id)})
            await self._mark_failed(wa_id, msg_id, f"{type(e).__name__}: {str(e)[:300]}")
            return msg_id is not None

    async def _mark_failed(self, wa_id: str, msg_id, error: str) -> None:
        if msg_id is None:
            return
        async with self.c.db.sessionmaker() as session, session.begin():
            msg = await session.get(Message, msg_id)
            if msg is None:
                return
            msg.processing_status, msg.error, msg.attempts = ProcessingStatus.FAILED, error, (msg.attempts or 0) + 1
            row = await self.c.whatsapp.queue(
                session, wa_id=wa_id, farmer_id=msg.farmer_id,
                payload={
                    "messaging_product": "whatsapp", "to": wa_id.lstrip("+"), "type": "text",
                    "text": {"preview_url": False, "body": M.GENERIC_ERROR},
                },
            )
            row.content = {**row.content, "text": M.GENERIC_ERROR, "in_window": True}

    async def _flush_outbox(self, wa_id: str) -> None:
        async with self.c.db.sessionmaker() as session, session.begin():
            await advisory_xact_lock(session, f"farmer:{wa_id}")
            rows = (
                await session.execute(
                    select(Message)
                    .where(Message.wa_id == wa_id, Message.direction == "OUTBOUND", Message.status == DeliveryStatus.QUEUED)
                    .order_by(Message.created_at, Message.id)
                )
            ).scalars().all()
            for row in rows:
                await self.c.whatsapp.deliver(session, row)
