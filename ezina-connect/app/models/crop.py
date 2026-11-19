from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin, UUIDPk


class FarmerCrop(UUIDPk, TimestampMixin, Base):
    __tablename__ = "farmer_crops"

    farm_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("farms.id", ondelete="CASCADE"), index=True)
    name_raw: Mapped[str] = mapped_column(String(200))  # as typed
    name_normalized: Mapped[str] = mapped_column(String(200), index=True)
    variety: Mapped[str | None] = mapped_column(String(200))
    season: Mapped[str | None] = mapped_column(String(100))

    farm = relationship("Farm", back_populates="crops", lazy="raise")
