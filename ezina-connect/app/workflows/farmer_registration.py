"""Applies Claude's extracted values / corrections to the draft, after Python validation."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.config import Settings
from app.enums import Stage
from app.schemas.ai_response import CORRECTABLE_FIELDS, AIResponse
from app.schemas.conversation import Draft
from app.workflows import address_flow
from app.workflows import validators as v
from app.workflows.validators import ValidationFailure

OPTIONAL_FIELDS = {"farm_name"}
FIELD_LABELS = {
    "full_name": "name",
    "country": "country",
    "full_address_text": "farm address",
    "farm_name": "farm name",
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
    elif name == "full_address_text":  # a confirmed (corrected) address replaces the old one as given
        draft.full_address_text = v.validate_address(value)
        draft.address_missing, draft.address_followups = [], 0
    elif name == "farm_name":
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
        followup = name == "full_address_text" and bool(draft.address_missing)  # answer to a missing-part question
        if already and not at_review and not followup:
            continue  # plain extraction never overwrites; only explicit corrections (or review edits) do
        incoming[name] = (val, already and not followup)
    for name, val in corrections.items():
        incoming[name] = (val, True)

    # The farm address is one text with its own rules (completeness follow-ups, correction confirmation).
    address = incoming.pop("full_address_text", None)
    if address is not None:
        _apply_address(draft, ai, address, stage, result)

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


def _apply_address(draft: Draft, ai: AIResponse, address: tuple[Any, bool], stage: Stage, result: ApplyResult) -> None:
    raw, is_correction = address
    followup = bool(draft.address_missing)
    try:
        if is_correction and draft.full_address_text and not followup:  # Claude rewrote the whole address: the farmer must confirm it before it replaces the old one
            result.confirm = {"type": "confirm_field", "field": "full_address_text",
                              "value": v.validate_address(address_flow.clean(raw))}
            return
        text = v.validate_address(address_flow.combine(draft.full_address_text if followup else None, str(raw)))
    except ValidationFailure as e:
        # an address mentioned in passing at another step is simply ignored; only the address question reports errors
        if stage == Stage.COLLECT_FARM_DETAILS:
            result.errors.append(e)
        return
    draft.full_address_text = text
    address_flow.apply_followup_rule(
        draft, address_flow.canonical_missing(ai.address_missing_parts, address_flow.format_for(draft.country))
    )
    result.changed.append("full_address_text")


def apply_pending_confirmed(draft: Draft, pending: dict[str, Any], settings: Settings) -> list[str]:
    try:
        _set(draft, pending["field"], pending["value"], settings)
    except (ValidationFailure, KeyError):
        return []
    return [pending["field"]]
