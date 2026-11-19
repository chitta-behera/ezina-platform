from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, JSONType, TimestampMixin, UUIDPk


class Message(UUIDPk, TimestampMixin, Base):
    """Every inbound and outbound WhatsApp message (audit log + processing queue + outbox)."""

    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("direction IN ('INBOUND','OUTBOUND')", name="ck_messages_direction"),
        CheckConstraint(
            "processing_status IN ('received','processing','processed','failed')",
            name="ck_messages_processing_status",
        ),
        Index("ix_messages_wa_id_processing", "wa_id", "processing_status"),
    )

    farmer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("farmers.id", ondelete="SET NULL"), index=True
    )
    wa_id: Mapped[str] = mapped_column(String(32), index=True)  # E.164 counterpart
    direction: Mapped[str] = mapped_column(String(10), index=True)
    wa_message_id: Mapped[str | None] = mapped_column(String(200), unique=True, index=True)
    type: Mapped[str] = mapped_column(String(30))
    content: Mapped[dict] = mapped_column(JSONType, default=dict)
    payload: Mapped[dict | None] = mapped_column(JSONType)  # outbound: Graph API request body
    # inbound: "received"; outbound: delivery state queued/sent/delivered/read/failed
    status: Mapped[str] = mapped_column(String(20), default="received", index=True)
    processing_status: Mapped[str] = mapped_column(String(20), default="received", index=True)
    wa_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
