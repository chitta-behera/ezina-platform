"""Draft (partially collected registration data) and outbound reply descriptions."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Draft(BaseModel):
    """Stored as JSONB in conversations.draft. Python-owned; Claude only ever sees a summary."""

    welcomed: bool = False
    detected_language: str | None = None
    detected_language_conf: float = 0.0

    full_name: str | None = None
    country: str | None = None  # ISO alpha-2
    preferred_language: str | None = None

    full_address_text: str | None = None  # one text; the individual parts are never stored
    address_followups: int = 0  # follow-up questions already asked for missing parts (max 2)
    address_missing: list[str] = Field(default_factory=list)  # parts still being asked for (labels only, transient)
    farm_name: str | None = None
    crops: list[str] = Field(default_factory=list)  # as typed
    cultivation_area: float | None = None
    area_unit: str | None = None  # acre | hectare | square_metre
    area_hectares: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    location_name: str | None = None
    location_address: str | None = None

    farm_photo_ids: list[str] = Field(default_factory=list)  # FarmDocument UUIDs
    crop_photo_ids: list[str] = Field(default_factory=list)
    location_skipped: bool = False
    farm_photos_skipped: bool = False
    crop_photos_skipped: bool = False

    # Identity verification. Only references (identity_documents ids), flags and counters: never an ID number,
    # never image data. Claude only ever sees "received / pending" (see ConversationService._collected).
    id_type: str | None = None  # code from config/id_documents.yaml
    id_back_required: bool = False
    id_front_doc: str | None = None  # IdentityDocument UUID
    id_back_doc: str | None = None
    id_attempts: int = 0  # failed uploads since the last accepted image
    id_deferred: bool = False  # "Send later"
    id_needs_help: bool = False  # too many failures / no usable ID -> operations follow-up
    selfie_doc: str | None = None
    selfie_attempts: int = 0
    selfie_deferred: bool = False
    selfie_needs_help: bool = False
    selfie_challenge: int | None = None  # fingers to hold up (1-5)
    selfie_challenge_at: datetime | None = None

    # awaiting a yes/no: {"type": "confirm_field", "field":..., "value":...} | {"type": "cancel"}
    pending: dict[str, Any] | None = None

    @property
    def id_received(self) -> bool:
        return bool(self.id_front_doc) and (bool(self.id_back_doc) or not self.id_back_required)

    @property
    def selfie_received(self) -> bool:
        return bool(self.selfie_doc)

    @property
    def has_location(self) -> bool:
        return self.latitude is not None and self.longitude is not None


@dataclass
class Button:
    id: str
    title: str  # <= 20 chars (WhatsApp limit)


@dataclass
class ListRow:
    id: str
    title: str  # <= 24 chars
    description: str | None = None


@dataclass
class Reply:
    """A channel-agnostic outbound message; converted to a Graph API payload by whatsapp_service."""

    body: str
    buttons: list[Button] = field(default_factory=list)
    list_rows: list[ListRow] = field(default_factory=list)
    list_button_label: str = "Choose"
