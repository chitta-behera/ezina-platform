"""Draft (partially collected registration data) and outbound reply descriptions."""
from __future__ import annotations

from dataclasses import dataclass, field
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

    village: str | None = None
    district: str | None = None
    farm_name: str | None = None
    farm_address: str | None = None
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

    # awaiting a yes/no: {"type": "confirm_field", "field":..., "value":...} | {"type": "cancel"}
    pending: dict[str, Any] | None = None

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
