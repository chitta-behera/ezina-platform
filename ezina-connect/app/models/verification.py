from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin, UUIDPk


class Verification(UUIDPk, TimestampMixin, Base):
    """History of verification decisions (append-only)."""

    __tablename__ = "verifications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','VERIFIED','REJECTED','NEEDS_MORE_INFO')", name="ck_verifications_status"
        ),
    )

    farmer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("farmers.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    reviewer: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
