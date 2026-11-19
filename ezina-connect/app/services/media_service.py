"""Downloads WhatsApp media immediately (URLs are temporary), validates, stores, records a FarmDocument."""
from __future__ import annotations

import hashlib
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.enums import DocumentType
from app.models import FarmDocument
from app.services.storage_service import StorageBackend
from app.services.whatsapp_service import WhatsAppError, WhatsAppService

log = logging.getLogger("ezina.media")
_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


class MediaRejected(Exception):
    def __init__(self, reason: str, user_message: str):
        super().__init__(reason)
        self.user_message = user_message


class MediaService:
    def __init__(self, settings: Settings, whatsapp: WhatsAppService, storage: StorageBackend):
        self.s, self.wa, self.storage = settings, whatsapp, storage

    async def ingest_image(
        self,
        session: AsyncSession,
        *,
        farmer_id: uuid.UUID,
        media_id: str,
        doc_type: DocumentType,
        caption: str | None,
        farm_id: uuid.UUID | None = None,
    ) -> FarmDocument:
        existing = (
            await session.execute(select(FarmDocument).where(FarmDocument.wa_media_id == media_id))
        ).scalar_one_or_none()
        if existing:  # idempotent on re-processing
            return existing

        try:
            meta = await self.wa.get_media_meta(media_id)
            mime = (meta.get("mime_type") or "").lower()
            if mime not in self.s.allowed_image_mime:
                raise MediaRejected("mime", "Sorry, I can only accept JPEG, PNG or WebP photos.")
            if int(meta.get("file_size") or 0) > self.s.max_media_bytes:
                raise MediaRejected("size", "That photo is too large. Please send a smaller one.")
            data = await self.wa.download_media(meta["url"])
        except WhatsAppError as e:
            log.error("media download failed", extra={"error": str(e)[:200]})
            raise MediaRejected("download", "Sorry, I couldn't receive that photo. Please try sending it again.") from e

        if len(data) > self.s.max_media_bytes:
            raise MediaRejected("size", "That photo is too large. Please send a smaller one.")

        key = f"farmers/{farmer_id}/{doc_type.value.lower()}/{uuid.uuid4()}.{_EXT[mime]}"
        await self.storage.put(key, data, mime)
        doc = FarmDocument(
            farmer_id=farmer_id, farm_id=farm_id, doc_type=doc_type.value, wa_media_id=media_id,
            storage_key=key, mime_type=mime, size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(), caption=(caption or None),
        )
        session.add(doc)
        await session.flush()
        return doc
