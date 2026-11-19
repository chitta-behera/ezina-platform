"""Reusable farm sub-flow: details -> crops -> area -> location -> photos.

Used by the registration flow now, and by ADD_FARM later (phase 2).
"""
from __future__ import annotations

from app.enums import Stage
from app.schemas.conversation import Draft


def next_farm_stage(draft: Draft, min_farm_photos: int) -> Stage | None:
    if not (draft.village and draft.district):
        return Stage.COLLECT_FARM_DETAILS
    if not draft.crops:
        return Stage.COLLECT_CROPS
    if draft.cultivation_area is None:
        return Stage.COLLECT_CULTIVATION_AREA
    if not draft.has_location and not draft.location_skipped:
        return Stage.COLLECT_GPS_LOCATION
    if len(draft.farm_photo_ids) < max(min_farm_photos, 1) and not draft.farm_photos_skipped:
        return Stage.COLLECT_FARM_PHOTOS
    if not draft.crop_photo_ids and not draft.crop_photos_skipped:
        return Stage.COLLECT_CROP_PHOTOS
    return None


def missing_farm_fields(draft: Draft) -> list[str]:
    out = []
    if not draft.village:
        out.append("village")
    if not draft.district:
        out.append("district")
    if not draft.crops:
        out.append("crops")
    if draft.cultivation_area is None:
        out.append("cultivation_area")
    return out
