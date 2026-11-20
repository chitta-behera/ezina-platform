"""Reusable farm sub-flow: address -> crops -> area -> location -> [ID document -> selfie] -> photos.

Used by the registration flow now, and by ADD_FARM later (phase 2).
"""
from __future__ import annotations

from app.enums import Stage
from app.schemas.conversation import Draft
from app.workflows import identity_flow


def next_farm_stage(draft: Draft, min_farm_photos: int, with_identity: bool = False) -> Stage | None:
    if not draft.full_address_text or draft.address_missing:  # one text; a pending follow-up keeps this stage open
        return Stage.COLLECT_FARM_DETAILS
    if not draft.crops:
        return Stage.COLLECT_CROPS
    if draft.cultivation_area is None:
        return Stage.COLLECT_CULTIVATION_AREA
    if not draft.has_location and not draft.location_skipped:
        return Stage.COLLECT_GPS_LOCATION
    if with_identity:  # registration only: ID document + selfie come right after the location
        stage = identity_flow.next_identity_stage(draft)
        if stage:
            return stage
    if len(draft.farm_photo_ids) < max(min_farm_photos, 1) and not draft.farm_photos_skipped:
        return Stage.COLLECT_FARM_PHOTOS
    if not draft.crop_photo_ids and not draft.crop_photos_skipped:
        return Stage.COLLECT_CROP_PHOTOS
    return None


def missing_farm_fields(draft: Draft) -> list[str]:
    out = []
    if not draft.full_address_text:
        out.append("full_address_text")
    if not draft.crops:
        out.append("crops")
    if draft.cultivation_area is None:
        out.append("cultivation_area")
    return out
