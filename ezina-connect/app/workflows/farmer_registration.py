"""Applies Claude's extracted values / corrections to the draft, after Python validation."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.config import Settings
from app.enums import Stage
from app.schemas.ai_response import CORRECTABLE_FIELDS, AIResponse
from app.schemas.conversation import Draft
from app.workflows import validators as v
from app.workflows.validators import ValidationFailure

OPTIONAL_FIELDS = {"farm_name", "farm_address"}
FIELD_LABELS = {
    "full_name": "name",
    "country": "country",
    "village": "village or town",
    "district": "district",
    "farm_name": "farm name",
    "farm_address": "farm address",
    "crops": "crops",
    "cultivation_area": "land size",
    "preferred_language": "language",
}


@dataclass
class ApplyResult:
    changed: list[str] = field(default_factory=list)
    errors: list[ValidationFailure] = field(default_factory=list)
    confirm: dict[str, Any] | None = None  # low-confidence value awaiting yes/no


def has_value(draft: Draft, name: str) -> bool:
    if name == "cultivation_area":
        return draft.cultivation_area is not None
    if name == "area_unit":
        return draft.area_unit is not None
    return bool(getattr(draft, name, None))


def _set(draft: Draft, name: str, value: Any, settings: Settings, extras: dict | None = None) -> None:
    """Validate and store one field. Raises ValidationFailure."""
    if name == "full_name":
        draft.full_name = v.validate_name(value)
    elif name == "country":
        draft.country = v.validate_country(value)
    elif name in ("village", "district"):
        setattr(draft, name, v.validate_place(name, value))
    elif name in ("farm_name", "farm_address"):
        setattr(draft, name, v.validate_optional_text(name, value, 500))
    elif name == "crops":
        draft.crops = v.validate_crops(value if isinstance(value, list) else [str(value)])
    elif name == "preferred_language":
        draft.preferred_language = v.validate_language(value, settings.supported_languages)
    elif name == "area":
        num, unit = value
        num_ok, canon, hectares = v.validate_area(num, unit)
        draft.cultivation_area, draft.area_unit, draft.area_hectares = num_ok, canon, hectares
    else:  # pragma: no cover - guarded by caller
        raise ValidationFailure(name, "unsupported field", "")


def apply_ai(draft: Draft, ai: AIResponse, stage: Stage, settings: Settings) -> ApplyResult:
    result = ApplyResult()
    provided = ai.extracted_data.provided()
    corrections = {c.field: c.new_value for c in ai.corrections if c.field in CORRECTABLE_FIELDS}
    at_review = stage == Stage.REVIEW_REGISTRATION

    # incoming: field -> (raw value, is_correction)
    incoming: dict[str, tuple[Any, bool]] = {}
    for name, val in provided.items():
        if name in corrections:
            continue
        already = has_value(draft, name)
        if already and not at_review:
            continue  # plain extraction never overwrites; only explicit corrections (or review edits) do
        incoming[name] = (val, already)
    for name, val in corrections.items():
        incoming[name] = (val, True)

    # Combine area fields into one validated unit of work.
    area_val = incoming.pop("cultivation_area", None)
    unit_val = incoming.pop("area_unit", None)
    if area_val or unit_val:
        num: Any = None
        unit: str | None = None
        is_corr = bool((area_val and area_val[1]) or (unit_val and unit_val[1]))
        if area_val:
            raw = area_val[0]
            if isinstance(raw, str):
                num, parsed_unit = v.parse_area_text(raw)
                unit = parsed_unit
            else:
                num = raw
        if unit_val:
            unit = str(unit_val[0])
        unit = unit or ai.extracted_data.area_unit or draft.area_unit
        if num is None:
            num = draft.cultivation_area
        incoming["area"] = ((num, unit), is_corr)

    for name, (val, is_corr) in incoming.items():
        conf_key = "cultivation_area" if name == "area" else name
        if not is_corr and ai.conf_for(conf_key) < settings.low_confidence_threshold and result.confirm is None:
            try:  # validate first so we only ask the farmer to confirm a plausible value
                probe = draft.model_copy(deep=True)
                _set(probe, name, val, settings)
            except ValidationFailure as e:
                if name not in OPTIONAL_FIELDS:
                    result.errors.append(e)
                continue
            result.confirm = {"type": "confirm_field", "field": name, "value": val}
            continue
        try:
            _set(draft, name, val, settings)
            result.changed.append(conf_key)
        except ValidationFailure as e:
            if name not in OPTIONAL_FIELDS:
                result.errors.append(e)
    return result


def apply_pending_confirmed(draft: Draft, pending: dict[str, Any], settings: Settings) -> list[str]:
    try:
        _set(draft, pending["field"], pending["value"], settings)
    except (ValidationFailure, KeyError):
        return []
    return [pending["field"]]
