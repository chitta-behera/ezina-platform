"""Structured response Claude must return (via a single forced tool)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.enums import HarvestReadiness, Intent

CORRECTABLE_FIELDS = (
    "full_name",
    "country",
    "farm_name",
    "full_address_text",
    "crops",
    "cultivation_area",
    "area_unit",
    "preferred_language",
)


class ExtractedData(BaseModel):
    full_name: str | None = None
    country: str | None = Field(None, description="Country name as the farmer said it, or ISO alpha-2 code")
    farm_name: str | None = None
    full_address_text: str | None = Field(
        None,
        description="The farm's address as ONE text, in the farmer's own words. While a follow-up for missing "
        "parts is open, only what the farmer said in this message (the program joins it to the earlier part). "
        "For a correction, the full corrected address.",
    )
    crops: list[str] = Field(default_factory=list, description="Crops the farmer grows, one entry per crop")
    cultivation_area: float | None = Field(None, description="Numeric land size")
    area_unit: str | None = Field(None, description="Unit exactly as said: acres, hectares, ha, sqm ...")
    preferred_language: str | None = Field(None, description="Language code the farmer asks to be served in")
    # harvest flow (phase 3)
    crop: str | None = None
    quantity: float | None = None
    quantity_unit: str | None = None
    bag_weight_kg: float | None = None
    expected_harvest_date: str | None = Field(None, description="ISO date YYYY-MM-DD resolved from current date")
    harvest_readiness: HarvestReadiness | None = None
    quality_grade: str | None = None
    expected_price: float | None = None
    price_currency: str | None = None

    def provided(self) -> dict[str, Any]:
        """Only the registration fields that are actually present."""
        out: dict[str, Any] = {}
        for name in CORRECTABLE_FIELDS:
            v = getattr(self, name)
            if v not in (None, "", []):
                out[name] = v
        return out


class Correction(BaseModel):
    field: str = Field(description="One of: " + ", ".join(CORRECTABLE_FIELDS))
    new_value: str


class AIResponse(BaseModel):
    intent: Intent
    extracted_data: ExtractedData = Field(default_factory=ExtractedData)
    corrections: list[Correction] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list, description="Advisory only")
    address_missing_parts: list[str] = Field(
        default_factory=list,
        description="Advisory only. Expected address parts (from address_format in the state) that are clearly "
        "missing from the farm address. Empty when the address is complete, or when a landmark is given.",
    )
    confidence: float = Field(ge=0, le=1, default=0.5)
    field_confidence: dict[str, float] = Field(default_factory=dict)
    requires_clarification: bool = False
    clarification_reason: str | None = None
    suggested_response: str = ""
    language: str = "en"

    @field_validator("extracted_data", mode="before")
    @classmethod
    def _none_to_empty(cls, v):
        return {} if v is None else v

    @field_validator("corrections", "missing_fields", "address_missing_parts", mode="before")
    @classmethod
    def _none_to_list(cls, v):
        return [] if v is None else v

    @field_validator("field_confidence", mode="before")
    @classmethod
    def _none_to_dict(cls, v):
        return {} if v is None else v

    def conf_for(self, field_name: str) -> float:
        return self.field_confidence.get(field_name, self.confidence)


def _inline_refs(schema: dict) -> dict:
    """Resolve $ref/$defs so the tool input_schema is a plain self-contained JSON schema."""
    defs = schema.get("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(defs[node["$ref"].split("/")[-1]])
            return {k: walk(v) for k, v in node.items() if k not in ("$defs", "title")}
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(schema)


def tool_input_schema() -> dict:
    schema = _inline_refs(AIResponse.model_json_schema())
    schema["required"] = ["intent", "suggested_response", "confidence", "language"]
    return schema
