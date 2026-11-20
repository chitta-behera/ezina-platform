from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin, UUIDPk


class Farm(UUIDPk, TimestampMixin, Base):
    __tablename__ = "farms"

    farmer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("farmers.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str | None] = mapped_column(String(200))
    full_address_text: Mapped[str] = mapped_column(Text)  # the whole address as one text; parts are never stored
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    location_name: Mapped[str | None] = mapped_column(String(300))
    location_address: Mapped[str | None] = mapped_column(String(500))
    cultivation_area: Mapped[float | None] = mapped_column(Float)  # as given by the farmer
    area_unit: Mapped[str | None] = mapped_column(String(20))  # as given (normalised unit name)
    area_hectares: Mapped[float | None] = mapped_column(Float)

    farmer = relationship("Farmer", back_populates="farms", lazy="raise")
    crops = relationship("FarmerCrop", back_populates="farm", cascade="all, delete-orphan", lazy="raise")
