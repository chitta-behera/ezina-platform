"""Identity images (ID document photos, selfies): download, Python checks, private storage, deletion.

Python decides whether an image is acceptable: MIME type, size, minimum resolution and a SHA-256 that no
earlier identity image (from any farmer) has used. No model looks at the image here. The images are stored in a
separate private bucket/prefix and are never given to Claude, never linked by URL and never captioned.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import uuid
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database import utcnow
from app.enums import FaceCheckStatus, IdentityDocStatus, IdentityKind, NameCheckStatus
from app.models import IdentityDocument
from app.services import name_match
from app.services.doc_extract_service import DocExtractError, DocExtractService
from app.services.face_verify_service import (
    FaceResult,
    FaceVerifyError,
    FaceVerifyService,
    classify,
    pdf_first_page_png,
)
from app.services.storage_service import StorageBackend
from app.services.whatsapp_service import WhatsAppError, WhatsAppService
from app.workflows import identity_flow

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

    # ------------------------------------------------------------------ name check (advisory, ID_FRONT only)
    async def extract_name(self, doc: IdentityDocument, extract: DocExtractService) -> NameCheckStatus:
        """Send the stored ID image to the extraction API and keep only the name on the row.

        SKIPPED when the check is off or this ID type has no configuration (no API call); ERROR when the API could
        not be used (the farmer is not blocked, operations review it); NOT_FOUND when the response had no name;
        otherwise PENDING, with `extracted_name` set, waiting for compare_name().
        """
        spec = identity_flow.extraction_for(doc.id_document_type)
        doc.name_check_status, doc.extracted_name, doc.name_match_score = NameCheckStatus.PENDING.value, None, None
        if not extract.available or spec is None:
            doc.name_check_status = NameCheckStatus.SKIPPED.value
            return NameCheckStatus.SKIPPED
        try:
            data = await self.storage.get(doc.storage_key)
            name = await extract.extract_name(
                doc_type=spec.doc_type, name_fields=list(spec.name_fields), data=data, mime=doc.mime_type
            )
        except Exception as e:  # DocExtractError, or the stored image could not be read: never block the farmer
            reason = e.reason if isinstance(e, DocExtractError) else type(e).__name__
            doc.name_check_status, doc.name_checked_at = NameCheckStatus.ERROR.value, utcnow()
            log.warning("name check error: flagged for operations review", extra={"reason": reason, "doc": str(doc.id)})
            return NameCheckStatus.ERROR
        doc.name_checked_at = utcnow()
        if not name:
            doc.name_check_status = NameCheckStatus.NOT_FOUND.value
            return NameCheckStatus.NOT_FOUND
        doc.extracted_name = name
        return NameCheckStatus.PENDING

    def compare_name(self, doc: IdentityDocument, given_name: str | None) -> NameCheckStatus:
        """Compare the farmer's name with the stored extracted name (no API call). Advisory: never verifies anyone."""
        status, score = name_match.compare(
            given_name, doc.extracted_name, threshold=self.s.name_match_threshold, partial=self.s.name_partial_threshold
        )
        doc.name_check_status, doc.name_match_score, doc.name_checked_at = status.value, score, utcnow()
        log.info("name check compared", extra={"status": status.value, "score": score, "doc": str(doc.id)})
        return status

    async def face_attempts(self, session: AsyncSession, farmer_id: uuid.UUID) -> int:
        """Failed face checks so far: the running total kept on the farmer's SELFIE rows (superseded ones included)."""
        top = (
            await session.execute(
                select(func.max(IdentityDocument.face_check_attempts)).where(
                    IdentityDocument.farmer_id == farmer_id, IdentityDocument.kind == IdentityKind.SELFIE.value
                )
            )
        ).scalar_one_or_none()
        return int(top or 0)

    # ------------------------------------------------------------------ face check (advisory, SELFIE only)
    @staticmethod
    def _set_face(selfie: IdentityDocument, status: FaceCheckStatus, result: FaceResult | None = None,
                  error: str | None = None) -> FaceCheckStatus:
        """Record the outcome on the selfie row. Only the listed fields are kept; the raw response never is."""
        r = result or FaceResult()
        selfie.face_check_status = status.value
        selfie.face_verified, selfie.face_distance, selfie.face_threshold = r.verified, r.distance, r.threshold
        selfie.face_confidence_band, selfie.face_liveness_passed = r.confidence_band, r.liveness_passed
        selfie.face_found_id, selfie.face_found_selfie = r.face_found_id, r.face_found_selfie
        selfie.face_model, selfie.face_detector, selfie.face_processing_ms = r.model, r.detector, r.processing_ms
        selfie.face_warnings = r.warnings or None
        selfie.face_error_message = error or r.error
        selfie.face_checked_at = utcnow()
        return status

    async def face_check(
        self, selfie: IdentityDocument, id_doc: IdentityDocument | None, verify: FaceVerifyService
    ) -> FaceCheckStatus:
        """Compare the selfie with the ID front's photo and keep the outcome on the selfie row.

        SKIPPED when the check is off or a PDF ID cannot be turned into an image; PENDING_ID when there is no
        accepted ID front yet (it runs when one is accepted); ERROR when the API could not be used (the farmer is
        never blocked; operations review it). Otherwise MATCHED / MISMATCH / NO_FACE_ID / NO_FACE_SELFIE /
        LIVENESS_FAILED, as interpreted by `classify`. Never verifies anyone.
        """
        selfie.face_compared_id_document_id = id_doc.id if id_doc is not None else None
        if not verify.available:
            return self._set_face(selfie, FaceCheckStatus.SKIPPED)
        if id_doc is None:
            return self._set_face(selfie, FaceCheckStatus.PENDING_ID)
        try:
            id_bytes, id_mime = await self.storage.get(id_doc.storage_key), id_doc.mime_type
            selfie_bytes = await self.storage.get(selfie.storage_key)
        except Exception as e:  # the stored image could not be read: never block the farmer
            log.warning("face check error: flagged for operations review", extra={"reason": type(e).__name__})
            return self._set_face(selfie, FaceCheckStatus.ERROR, error=type(e).__name__)
        if id_mime == "application/pdf":  # the API takes images: send the first page
            try:
                id_bytes, id_mime = await asyncio.to_thread(pdf_first_page_png, id_bytes), "image/png"
            except Exception as e:
                log.warning("face check skipped: PDF could not be converted", extra={"reason": type(e).__name__})
                return self._set_face(selfie, FaceCheckStatus.SKIPPED, error="pdf_conversion_failed")
        try:
            result = await verify.verify(
                id_image=id_bytes, id_mime=id_mime, selfie_image=selfie_bytes, selfie_mime=selfie.mime_type
            )
        except FaceVerifyError as e:
            log.warning("face check error: flagged for operations review", extra={"reason": e.reason})
            return self._set_face(selfie, FaceCheckStatus.ERROR, error=e.reason)
        status = classify(result)
        if status == FaceCheckStatus.ERROR:
            log.warning("face check error: flagged for operations review", extra={"reason": "api_error_or_no_verdict"})
        log.info("face check result", extra={"status": status.value})
        return self._set_face(selfie, status, result)

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
