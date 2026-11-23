from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, JSONType, TimestampMixin, UUIDPk, utcnow


class IdentityDocument(UUIDPk, TimestampMixin, Base):
    """ID card photos and selfies. Sensitive: kept apart from farm_documents, stored in the private identity bucket.

    Never holds an ID number, a caption or a raw API response. The only text read from an image is
    `extracted_name` (the name printed on the ID), kept for the operations review: sensitive, never logged, never sent
    to Claude, returned only by the admin farmer-detail endpoint.
    """

    __tablename__ = "identity_documents"
    __table_args__ = (
        CheckConstraint("kind IN ('ID_FRONT','ID_BACK','SELFIE')", name="ck_identity_documents_kind"),
        CheckConstraint("status IN ('ACCEPTED','REJECTED','SUPERSEDED')", name="ck_identity_documents_status"),
        CheckConstraint(
            "name_check_status IS NULL OR name_check_status IN "
            "('PENDING','MATCHED','PARTIAL','MISMATCH','NOT_FOUND','ERROR','SKIPPED')",
            name="ck_identity_documents_name_check_status",
        ),
        CheckConstraint(
            "face_check_status IS NULL OR face_check_status IN "
            "('PENDING_ID','MATCHED','MISMATCH','NO_FACE_ID','NO_FACE_SELFIE','LIVENESS_FAILED','ERROR','SKIPPED')",
            name="ck_identity_documents_face_check_status",
        ),
        CheckConstraint(  # the face check belongs to the selfie: no other kind may carry any of it
            "kind = 'SELFIE' OR (face_check_status IS NULL AND face_compared_id_document_id IS NULL AND "
            "face_verified IS NULL AND face_distance IS NULL AND face_threshold IS NULL AND "
            "face_confidence_band IS NULL AND face_liveness_passed IS NULL AND face_found_id IS NULL AND "
            "face_found_selfie IS NULL AND face_model IS NULL AND face_detector IS NULL AND "
            "face_processing_ms IS NULL AND face_warnings IS NULL AND face_error_message IS NULL AND "
            "face_checked_at IS NULL AND face_check_attempts = 0)",
            name="ck_identity_documents_face_only_selfie",
        ),
    )

    farmer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("farmers.id", ondelete="CASCADE"), index=True)
    country: Mapped[str | None] = mapped_column(String(2))
    kind: Mapped[str] = mapped_column(String(10), index=True)
    id_document_type: Mapped[str | None] = mapped_column(String(30))  # ID kinds only, e.g. OMANG
    wa_media_id: Mapped[str | None] = mapped_column(String(100), index=True)
    storage_key: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # reuse detection across all farmers
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    challenge: Mapped[str | None] = mapped_column(String(100))  # selfie: liveness challenge issued
    challenge_issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quality_result: Mapped[dict | None] = mapped_column(JSONType)  # Python checks (and later the vision check)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(12), default="ACCEPTED", index=True)

    # Name check (ID_FRONT only): the name printed on the ID compared with the name the farmer gave. Advisory.
    name_check_status: Mapped[str | None] = mapped_column(String(10), index=True)
    name_match_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    extracted_name: Mapped[str | None] = mapped_column(Text)
    name_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    name_check_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Face check (SELFIE rows only; NULL on other kinds): the selfie compared with the ID front's photo. Advisory.
    # Only the fields below are kept from the API response; the scores are for the operations team, never the farmer.
    face_check_status: Mapped[str | None] = mapped_column(String(16), index=True)
    face_compared_id_document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("identity_documents.id", ondelete="SET NULL", name="fk_identity_documents_face_compared_id")
        # the ID_FRONT row used for the comparison
    )
    face_verified: Mapped[bool | None] = mapped_column(Boolean)
    face_distance: Mapped[float | None] = mapped_column(Numeric(8, 5))
    face_threshold: Mapped[float | None] = mapped_column(Numeric(8, 5))
    face_confidence_band: Mapped[str | None] = mapped_column(Text)
    face_liveness_passed: Mapped[bool | None] = mapped_column(Boolean)
    face_found_id: Mapped[bool | None] = mapped_column(Boolean)
    face_found_selfie: Mapped[bool | None] = mapped_column(Boolean)
    face_model: Mapped[str | None] = mapped_column(Text)
    face_detector: Mapped[str | None] = mapped_column(Text)
    face_processing_ms: Mapped[float | None] = mapped_column(Numeric(12, 1))
    face_warnings: Mapped[list | None] = mapped_column(JSONType)
    face_error_message: Mapped[str | None] = mapped_column(Text)
    face_check_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # running total
    face_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
