"""COLLECT_ID_DOCUMENT and COLLECT_SELFIE: pure, deterministic logic (no I/O).

Reused by registration and by the later "send my ID/selfie" flow (SUBMIT_IDENTITY_DOCUMENTS). Claude never takes
part in these decisions; it never sees identity images or anything read from them.
"""
from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import yaml

from app.enums import IdentityStatus, Stage
from app.schemas.conversation import Draft

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "id_documents.yaml"
IDENTITY_STAGES = (Stage.COLLECT_ID_DOCUMENT, Stage.COLLECT_SELFIE)
CHALLENGE_RANGE = (1, 5)


@dataclass(frozen=True)
class IdType:
    code: str
    names: dict[str, str]
    back: bool
    mask: bool

    def name(self, lang: str | None = None) -> str:
        return self.names.get((lang or "en").lower()) or self.names["en"]


@lru_cache
def _load() -> dict[str, list[IdType]]:
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    out: dict[str, list[IdType]] = {}
    for country, spec in (raw.get("countries") or {}).items():
        out[country.upper()] = [
            IdType(t["code"], dict(t["names"]), bool(t.get("back", False)), bool(t.get("mask", False)))
            for t in spec.get("types", [])
        ]
    return out


def id_types(country: str | None) -> list[IdType]:
    return list(_load().get((country or "").upper(), []))


def find_type(country: str | None, code: str | None) -> IdType | None:
    return next((t for t in id_types(country) if t.code == code), None)


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (text or "").lower()).strip()


def match_type_text(country: str | None, text: str) -> IdType | None:
    """Deterministic match of a typed ID type ("omang", "driving license") to the country's list."""
    low = _squash(text).replace("license", "licence")
    if not low:
        return None
    for t in id_types(country):
        for n in t.names.values():
            n = _squash(n)
            if low in (n, t.code.lower().replace("_", " "), n.split(" ")[0]):
                return t
    return None


# ------------------------------------------------------------------ stage logic
def id_applicable(draft: Draft) -> bool:
    """False when Ezina has no ID types for the farmer's country: operations follow up instead (NEEDS_HELP)."""
    return not draft.country or bool(id_types(draft.country))


def id_resolved(draft: Draft) -> bool:
    return (not id_applicable(draft)) or draft.id_received or draft.id_deferred or draft.id_needs_help


def selfie_resolved(draft: Draft) -> bool:
    return draft.selfie_received or draft.selfie_deferred or draft.selfie_needs_help


def next_identity_stage(draft: Draft) -> Stage | None:
    if not id_resolved(draft):
        return Stage.COLLECT_ID_DOCUMENT
    if not selfie_resolved(draft):
        return Stage.COLLECT_SELFIE
    return None


def id_status(draft: Draft) -> IdentityStatus:
    if draft.id_received:
        return IdentityStatus.RECEIVED
    if draft.id_deferred:
        return IdentityStatus.DEFERRED
    if draft.id_needs_help or not id_applicable(draft):
        return IdentityStatus.NEEDS_HELP
    return IdentityStatus.NOT_PROVIDED


def selfie_status(draft: Draft) -> IdentityStatus:
    if draft.selfie_received:
        return IdentityStatus.RECEIVED
    if draft.selfie_deferred:
        return IdentityStatus.DEFERRED
    if draft.selfie_needs_help:
        return IdentityStatus.NEEDS_HELP
    return IdentityStatus.NOT_PROVIDED


def reset_id(draft: Draft) -> None:
    draft.id_type, draft.id_back_required = None, False
    draft.id_front_doc = draft.id_back_doc = None
    draft.id_attempts = 0
    draft.id_deferred = draft.id_needs_help = False


def select_type(draft: Draft, id_type: IdType) -> None:
    reset_id(draft)
    draft.id_type, draft.id_back_required = id_type.code, id_type.back


# ------------------------------------------------------------------ liveness challenge
def challenge_text(n: int) -> str:
    return f"hold up *{n} finger{'s' if n != 1 else ''}* next to your face"


def issue_challenge(draft: Draft, now: datetime) -> int:
    """New random challenge (1-5), different from the previous one."""
    options = [n for n in range(CHALLENGE_RANGE[0], CHALLENGE_RANGE[1] + 1) if n != draft.selfie_challenge]
    draft.selfie_challenge = secrets.choice(options)
    draft.selfie_challenge_at = now
    return draft.selfie_challenge


def challenge_expired(draft: Draft, at: datetime, ttl_minutes: int) -> bool:
    """True when there is no challenge, or `at` (the selfie's arrival time) is past the challenge's lifetime."""
    if draft.selfie_challenge is None or draft.selfie_challenge_at is None:
        return True
    issued = draft.selfie_challenge_at
    issued = issued if issued.tzinfo else issued.replace(tzinfo=UTC)
    return at - issued > timedelta(minutes=ttl_minutes)
