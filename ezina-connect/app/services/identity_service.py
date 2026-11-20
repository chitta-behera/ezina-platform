"""Identity images (ID document photos, selfies): download, Python checks, private storage, deletion.

Python decides whether an image is acceptable: MIME type, size, minimum resolution and a SHA-256 that no
earlier identity image (from any farmer) has used. No model looks at the image here. The images are stored in a
separate private bucket/prefix and are never given to Claude, never linked by URL and never captioned.
"""
from __future__ import annotations

import hashlib
import io
import logging
import uuid
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.enums import IdentityDocStatus, IdentityKind
from app.models import IdentityDocument
from app.services.storage_service import StorageBackend
from app.services.whatsapp_service import WhatsAppError, WhatsAppService

log = logging.getLogger("ezina.identity")
_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "application/pdf": "pdf"}
_PIL_MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


class IdentityRejected(Exception):
    """The image cannot be used. `user_message` is the one thing the farmer should fix."""

    def __init__(self, reason: str, user_message: str, counts_as_attempt: bool = True):
        super().__init__(reason)
        self.reason, self.user_message, self.counts_as_attempt = reason, user_message, counts_as_attempt


def _what(kind: IdentityKind) -> str:
    return "your face" if kind == IdentityKind.SELFIE else "the ID card"


def inspect_image(data: bytes, mime: str, kind: IdentityKind, min_px: int) -> dict:
    """Python-only quality checks on the bytes. Returns the check results, or raises IdentityRejected."""
    if mime == "application/pdf":
        if not data.startswith(b"%PDF-"):
            raise IdentityRejected("unreadable", "I couldn't open that file. Please send a clear photo of the ID instead.")
        return {"mime": mime, "resolution_checked": False}
    from PIL import Image  # Pillow: reads the dimensions only

    try:
        with Image.open(io.BytesIO(data)) as img:
            fmt, (w, h) = img.format, img.size
    except Exception:
        raise IdentityRejected("unreadable", "I couldn't open that photo. Please take a new photo and send it again.")
    if _PIL_MIME.get(fmt or "") != mime:
        raise IdentityRejected("unreadable", "I couldn't open that photo. Please take a new photo and send it again.")
    if min(w, h) < min_px:
        raise IdentityRejected(
            "low_resolution",
            f"The photo is too small to read. Please hold the phone closer to {_what(kind)} and take a new photo in good light.",
        )
    return {"mime": mime, "width": w, "height": h, "min_px": min_px, "resolution_checked": True}


class IdentityService:
    def __init__(self, settings: Settings, whatsapp: WhatsAppService, storage: StorageBackend):
        self.s, self.wa, self.storage = settings, whatsapp, storage

    async def ingest(
        self,
        session: AsyncSession,
        *,
        farmer_id: uuid.UUID,
        country: str | None,
        kind: IdentityKind,
        id_document_type: str | None,
        media_id: str,
        attempt: int,
        challenge: int | None = None,
        challenge_issued_at: datetime | None = None,
    ) -> IdentityDocument:
        existing = (
            await session.execute(select(IdentityDocument).where(IdentityDocument.wa_media_id == media_id))
        ).scalar_one_or_none()
        if existing:  # idempotent when a message is re-processed after a restart
            return existing

        allowed = set(self.s.identity_allowed_mime)
        if kind != IdentityKind.SELFIE:
            allowed |= set(self.s.identity_document_mime)  # an ID may also arrive as a document (image or PDF)
        try:
            meta = await self.wa.get_media_meta(media_id)
            mime = (meta.get("mime_type") or "").lower().split(";")[0].strip()
            if mime not in allowed:
                raise IdentityRejected("mime", "Sorry, I can only accept a JPEG or PNG photo" + (
                    "" if kind == IdentityKind.SELFIE else " (or a PDF)") + ". Please send it again.")
            if int(meta.get("file_size") or 0) > self.s.identity_max_bytes:
                raise IdentityRejected("size", "That file is too large. Please send a smaller photo.")
            data = await self.wa.download_media(meta["url"])
        except WhatsAppError as e:
            log.error("identity media download failed", extra={"error": str(e)[:200]})
            raise IdentityRejected("download", "Sorry, I couldn't receive that. Please send it again.", False) from e
        if len(data) > self.s.identity_max_bytes:
            raise IdentityRejected("size", "That file is too large. Please send a smaller photo.")

        quality = inspect_image(data, mime, kind, self.s.identity_min_image_px)
        digest = hashlib.sha256(data).hexdigest()
        if (await session.execute(select(IdentityDocument.id).where(IdentityDocument.sha256 == digest))).first():
            raise IdentityRejected("duplicate", "That photo has already been used. Please take a new photo now.")

        key = f"identity/{farmer_id}/{kind.value.lower()}/{uuid.uuid4()}.{_EXT[mime]}"
        await self.storage.put(key, data, mime)
        doc = IdentityDocument(
            farmer_id=farmer_id, country=country, kind=kind.value, id_document_type=id_document_type,
            wa_media_id=media_id, storage_key=key, mime_type=mime, size_bytes=len(data), sha256=digest,
            challenge=(f"{challenge} fingers" if challenge else None), challenge_issued_at=challenge_issued_at,
            quality_result=quality, attempt=attempt, status=IdentityDocStatus.ACCEPTED.value,
        )
        try:
            async with session.begin_nested():
                await self.supersede(session, farmer_id, kind)
                session.add(doc)
        except IntegrityError:  # another upload of the same image won the race on the unique hash
            await self.storage.delete(key)
            raise IdentityRejected("duplicate", "That photo has already been used. Please take a new photo now.")
        await session.flush()
        log.info("identity image accepted", extra={"kind": kind.value, "bytes": len(data), "attempt": attempt})
        return doc

    async def supersede(self, session: AsyncSession, farmer_id: uuid.UUID, kind: IdentityKind) -> None:
        """Mark earlier ACCEPTED images replaced (ID_FRONT replaces the whole ID: front and back)."""
        kinds = [IdentityKind.ID_FRONT, IdentityKind.ID_BACK] if kind == IdentityKind.ID_FRONT else [kind]
        rows = (
            await session.execute(
                select(IdentityDocument).where(
                    IdentityDocument.farmer_id == farmer_id,
                    IdentityDocument.kind.in_([k.value for k in kinds]),
                    IdentityDocument.status == IdentityDocStatus.ACCEPTED.value,
                )
            )
        ).scalars().all()
        for r in rows:
            r.status = IdentityDocStatus.SUPERSEDED.value

    async def accepted(self, session: AsyncSession, farmer_id: uuid.UUID) -> dict[str, IdentityDocument]:
        """Latest ACCEPTED document per kind."""
        rows = (
            await session.execute(
                select(IdentityDocument)
                .where(IdentityDocument.farmer_id == farmer_id, IdentityDocument.status == IdentityDocStatus.ACCEPTED.value)
                .order_by(IdentityDocument.created_at)
            )
        ).scalars().all()
        return {r.kind: r for r in rows}

    async def delete_all(self, session: AsyncSession, farmer_id: uuid.UUID) -> int:
        """Hard-delete a farmer's identity images from storage and their rows (cancellation, data deletion)."""
        rows = (
            await session.execute(select(IdentityDocument).where(IdentityDocument.farmer_id == farmer_id))
        ).scalars().all()
        for r in rows:
            await self.storage.delete(r.storage_key)
        if rows:
            await session.execute(delete(IdentityDocument).where(IdentityDocument.farmer_id == farmer_id))
        return len(rows)
