from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, JSONType, TimestampMixin, UUIDPk, utcnow


class IdentityDocument(UUIDPk, TimestampMixin, Base):
    """ID card photos and selfies. Sensitive: kept apart from farm_documents, stored in the private identity bucket.

    Never holds an ID number, a caption or any text read from the image.
    """

    __tablename__ = "identity_documents"
    __table_args__ = (
        CheckConstraint("kind IN ('ID_FRONT','ID_BACK','SELFIE')", name="ck_identity_documents_kind"),
        CheckConstraint("status IN ('ACCEPTED','REJECTED','SUPERSEDED')", name="ck_identity_documents_status"),
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
