from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin, UUIDPk


class Farmer(UUIDPk, TimestampMixin, Base):
    __tablename__ = "farmers"
    __table_args__ = (
        CheckConstraint(
            "registration_status IN ('NOT_STARTED','IN_PROGRESS','SUBMITTED','CANCELLED')",
            name="ck_farmers_registration_status",
        ),
        CheckConstraint(
            "verification_status IN ('NOT_SUBMITTED','PENDING','VERIFIED','REJECTED','NEEDS_MORE_INFO')",
            name="ck_farmers_verification_status",
        ),
    )

    wa_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)  # E.164
    profile_name: Mapped[str | None] = mapped_column(String(200))
    full_name: Mapped[str | None] = mapped_column(String(200))
    country: Mapped[str | None] = mapped_column(String(2))  # ISO 3166-1 alpha-2
    preferred_language: Mapped[str | None] = mapped_column(String(10))
    consent_given: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    registration_status: Mapped[str] = mapped_column(String(20), default="NOT_STARTED", index=True)
    verification_status: Mapped[str] = mapped_column(String(20), default="NOT_SUBMITTED", index=True)
    opted_out: Mapped[bool] = mapped_column(Boolean, default=False)
    opted_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # data-deletion support
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    anonymized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    farms = relationship("Farm", back_populates="farmer", cascade="all, delete-orphan", lazy="raise")
