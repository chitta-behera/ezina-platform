from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, JSONType, TimestampMixin, UUIDPk


class Conversation(UUIDPk, TimestampMixin, Base):
    __tablename__ = "conversations"

    farmer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("farmers.id", ondelete="CASCADE"), unique=True, index=True
    )
    stage: Mapped[str] = mapped_column(String(40), default="START", index=True)
    resume_stage: Mapped[str | None] = mapped_column(String(40))  # stage to restore after handoff
    active_flow: Mapped[str | None] = mapped_column(String(40))  # registration | add_farm | harvest
    draft: Mapped[dict] = mapped_column(JSONType, default=dict)  # partially collected data
    language: Mapped[str | None] = mapped_column(String(10))
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_interaction_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_processed_wa_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    handoff: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    handoff_reason: Mapped[str | None] = mapped_column(Text)
    handoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
