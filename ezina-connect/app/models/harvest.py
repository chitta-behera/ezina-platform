from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, Float, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin, UUIDPk


class Harvest(UUIDPk, TimestampMixin, Base):
    """Harvest availability declared by a farmer (workflow arrives in phase 3)."""

    __tablename__ = "harvests"
    __table_args__ = (
        CheckConstraint(
            "readiness IS NULL OR readiness IN ('READY_NOW','WITHIN_2_WEEKS','LATER')",
            name="ck_harvests_readiness",
        ),
    )

    farmer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("farmers.id", ondelete="CASCADE"), index=True)
    farm_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("farms.id", ondelete="CASCADE"), index=True)
    crop_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("farmer_crops.id", ondelete="CASCADE"), index=True)
    quantity: Mapped[float | None] = mapped_column(Float)
    quantity_unit: Mapped[str | None] = mapped_column(String(30))
    bag_weight_kg: Mapped[float | None] = mapped_column(Float)
    expected_harvest_date: Mapped[date | None] = mapped_column(Date, index=True)
    readiness: Mapped[str | None] = mapped_column(String(20))
    quality_grade: Mapped[str | None] = mapped_column(String(50))
    expected_price: Mapped[float | None] = mapped_column(Float)
    price_currency: Mapped[str | None] = mapped_column(String(3))
    availability_location: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="CONFIRMED", index=True)
