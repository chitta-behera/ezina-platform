"""Deterministic stage resolution. Python decides the stage; Claude never does."""
from __future__ import annotations

from app.enums import Stage
from app.schemas.conversation import Draft
from app.workflows import farm_flow

CONTROL_STAGES = {Stage.HUMAN_HANDOFF, Stage.CANCELLED, Stage.COMPLETED}
# Stages entered/left by explicit events (consent, start); data stages are derived from the draft.
EVENT_STAGES = {Stage.START, Stage.CONSENT}

ORDER = [
    Stage.START,
    Stage.CONSENT,
    Stage.SELECT_LANGUAGE,
    Stage.COLLECT_NAME,
    Stage.COLLECT_COUNTRY,
    Stage.COLLECT_FARM_DETAILS,
    Stage.COLLECT_CROPS,
    Stage.COLLECT_CULTIVATION_AREA,
    Stage.COLLECT_GPS_LOCATION,
    Stage.COLLECT_ID_DOCUMENT,
    Stage.COLLECT_SELFIE,
    Stage.COLLECT_FARM_PHOTOS,
    Stage.COLLECT_CROP_PHOTOS,
    Stage.REVIEW_REGISTRATION,
    Stage.COMPLETED,
]

# The field name Python wants collected next (passed to Claude as a hint).
NEXT_FIELD = {
    Stage.SELECT_LANGUAGE: "preferred_language",
    Stage.COLLECT_NAME: "full_name",
    Stage.COLLECT_COUNTRY: "country",
    Stage.COLLECT_FARM_DETAILS: "full_address_text (the farm's full address as one text)",
    Stage.COLLECT_CROPS: "crops",
    Stage.COLLECT_CULTIVATION_AREA: "cultivation_area and area_unit",
    Stage.COLLECT_GPS_LOCATION: "WhatsApp location share (optional)",
    Stage.COLLECT_ID_DOCUMENT: "photo of the ID document (the program asks; never an ID number)",
    Stage.COLLECT_SELFIE: "live selfie (the program asks)",
    Stage.COLLECT_FARM_PHOTOS: "farm photo (optional)",
    Stage.COLLECT_CROP_PHOTOS: "crop photo (optional)",
    Stage.REVIEW_REGISTRATION: "confirmation of the summary",
}

OPTIONAL_STAGES = {Stage.COLLECT_GPS_LOCATION, Stage.COLLECT_FARM_PHOTOS, Stage.COLLECT_CROP_PHOTOS}


def registration_stage(draft: Draft, min_farm_photos: int) -> Stage:
    """First incomplete data stage, or REVIEW when everything is collected/skipped."""
    if not draft.preferred_language:
        return Stage.SELECT_LANGUAGE
    if not draft.full_name:
        return Stage.COLLECT_NAME
    if not draft.country:
        return Stage.COLLECT_COUNTRY
    return farm_flow.next_farm_stage(draft, min_farm_photos, with_identity=True) or Stage.REVIEW_REGISTRATION


def resolve_stage(current: Stage, draft: Draft, min_farm_photos: int) -> Stage:
    if current in CONTROL_STAGES or current in EVENT_STAGES:
        return current
    return registration_stage(draft, min_farm_photos)


def successor(stage: Stage) -> Stage:
    """The stage that normally follows `stage` when a single answer is accepted."""
    try:
        return ORDER[ORDER.index(stage) + 1]
    except (ValueError, IndexError):
        return stage


def missing_fields(draft: Draft, min_farm_photos: int) -> list[str]:
    out = []
    if not draft.full_name:
        out.append("full_name")
    if not draft.country:
        out.append("country")
    out += farm_flow.missing_farm_fields(draft)
    return out
