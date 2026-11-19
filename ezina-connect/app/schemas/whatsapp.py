"""Pydantic models for Meta WhatsApp Cloud API webhook payloads + a normalised inbound form."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_E164 = re.compile(r"^\+[1-9]\d{7,14}$")


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class WAProfile(_Base):
    name: str | None = None


class WAContact(_Base):
    wa_id: str
    profile: WAProfile | None = None


class WAText(_Base):
    body: str


class WALocation(_Base):
    latitude: float
    longitude: float
    name: str | None = None
    address: str | None = None


class WAMedia(_Base):
    id: str
    mime_type: str | None = None
    sha256: str | None = None
    caption: str | None = None


class WAReply(_Base):
    id: str
    title: str | None = None
    description: str | None = None


class WAInteractive(_Base):
    type: str
    button_reply: WAReply | None = None
    list_reply: WAReply | None = None


class WAButton(_Base):
    payload: str | None = None
    text: str | None = None


class WAMessage(_Base):
    id: str
    from_: str = Field(alias="from")
    timestamp: str
    type: str
    text: WAText | None = None
    location: WALocation | None = None
    image: WAMedia | None = None
    interactive: WAInteractive | None = None
    button: WAButton | None = None


class WAStatusError(_Base):
    code: int | None = None
    title: str | None = None
    message: str | None = None


class WAStatus(_Base):
    id: str
    status: str
    timestamp: str | None = None
    recipient_id: str | None = None
    errors: list[WAStatusError] = []


class WAValue(_Base):
    messaging_product: str | None = None
    contacts: list[WAContact] = []
    messages: list[WAMessage] = []
    statuses: list[WAStatus] = []


class WAChange(_Base):
    field: str | None = None
    value: WAValue


class WAEntry(_Base):
    id: str | None = None
    changes: list[WAChange] = []


class WebhookPayload(_Base):
    object: str | None = None
    entry: list[WAEntry] = []


def to_e164(raw: str) -> str:
    """WhatsApp wa_ids are digits only; store as +<digits>. Raises ValueError if implausible."""
    digits = re.sub(r"\D", "", raw or "")
    candidate = f"+{digits}"
    if not _E164.match(candidate):
        raise ValueError("invalid phone number")
    return candidate


@dataclass
class NormalizedInbound:
    wa_id: str
    wa_message_id: str
    wa_timestamp: datetime
    type: str  # text | location | image | interactive | button | unsupported:<type>
    profile_name: str | None = None
    text: str | None = None
    button_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    location_name: str | None = None
    location_address: str | None = None
    media_id: str | None = None
    mime_type: str | None = None
    caption: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_content(self) -> dict[str, Any]:
        d = {
            "text": self.text,
            "button_id": self.button_id,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "location_name": self.location_name,
            "location_address": self.location_address,
            "media_id": self.media_id,
            "mime_type": self.mime_type,
            "caption": self.caption,
            "profile_name": self.profile_name,
        }
        return {k: v for k, v in d.items() if v is not None}


SUPPORTED_TYPES = {"text", "location", "image", "interactive", "button"}


def normalize_message(msg: WAMessage, profile_name: str | None) -> NormalizedInbound:
    ts = datetime.fromtimestamp(int(msg.timestamp), tz=UTC)
    n = NormalizedInbound(
        wa_id=to_e164(msg.from_),
        wa_message_id=msg.id,
        wa_timestamp=ts,
        type=msg.type,
        profile_name=profile_name,
    )
    if msg.type == "text" and msg.text:
        n.text = msg.text.body
    elif msg.type == "location" and msg.location:
        n.latitude, n.longitude = msg.location.latitude, msg.location.longitude
        n.location_name, n.location_address = msg.location.name, msg.location.address
    elif msg.type == "image" and msg.image:
        n.media_id, n.mime_type, n.caption = msg.image.id, msg.image.mime_type, msg.image.caption
    elif msg.type == "interactive" and msg.interactive:
        reply = msg.interactive.button_reply or msg.interactive.list_reply
        if reply:
            n.button_id, n.text = reply.id, reply.title
    elif msg.type == "button" and msg.button:
        n.button_id, n.text = msg.button.payload, msg.button.text
    elif msg.type not in SUPPORTED_TYPES:
        pass  # audio, video, document, sticker, reaction, ... persisted as-is; handled politely later
    return n
