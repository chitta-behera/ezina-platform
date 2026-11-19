from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin, UUIDPk, utcnow


class FarmDocument(UUIDPk, TimestampMixin, Base):
    __tablename__ = "farm_documents"
    __table_args__ = (
        CheckConstraint("doc_type IN ('FARM_PHOTO','CROP_PHOTO','OTHER')", name="ck_farm_documents_type"),
    )

    farmer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("farmers.id", ondelete="CASCADE"), index=True)
    farm_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("farms.id", ondelete="SET NULL"), index=True
    )
    crop_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("farmer_crops.id", ondelete="SET NULL"), index=True
    )
    doc_type: Mapped[str] = mapped_column(String(20), index=True)
    wa_media_id: Mapped[str | None] = mapped_column(String(100), index=True)
    storage_key: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    caption: Mapped[str | None] = mapped_column(String(1024))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
