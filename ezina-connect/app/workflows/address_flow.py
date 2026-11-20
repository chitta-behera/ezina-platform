"""Farm address collection: pure, deterministic logic (no I/O).

The farm address is ONE free-text value. Claude checks it against the expected parts for the farmer's country and
lists what is clearly missing (advisory); Python decides whether to ask a follow-up (at most MAX_FOLLOWUPS), joins the
answers into one text, and never stores the individual parts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from app.schemas.conversation import Draft

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "address_formats.yaml"
MAX_FOLLOWUPS = 2
MAX_MISSING_PARTS = 3


@dataclass(frozen=True)
class AddressFormat:
    expected: tuple[str, ...]
    helpful: tuple[str, ...]
    instruction: str
    example: str

    def for_claude(self) -> dict:
        return {
            "expected_parts": list(self.expected), "helpful_parts": list(self.helpful),
            "instruction": self.instruction, "example": self.example,
        }


def _fmt(spec: dict) -> AddressFormat:
    return AddressFormat(
        tuple(spec["expected"]), tuple(spec.get("helpful", [])), spec["instruction"].strip(), spec["example"].strip()
    )


@lru_cache
def _load() -> tuple[AddressFormat, dict[str, AddressFormat]]:
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    return _fmt(raw["default"]), {k.upper(): _fmt(v) for k, v in (raw.get("countries") or {}).items()}


def format_for(country: str | None) -> AddressFormat:
    default, by_country = _load()
    return by_country.get((country or "").upper(), default)


def clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def combine(previous: str | None, new: str) -> str:
    """Join a follow-up answer to the address collected so far (one text, no parts stored)."""
    prev, add = clean(previous), clean(new)
    if not prev:
        return add
    if prev.lower() in add.lower():  # the farmer (or Claude) re-sent the whole address
        return add
    if add.lower() in prev.lower():
        return prev
    return f"{prev.rstrip(' ,;.')}, {add.lstrip(' ,;')}"


def _tokens(part: str) -> set[str]:
    return {t for t in re.split(r"[/ ]+", part.lower()) if t and t not in {"a", "and", "or", "number"}}


def canonical_missing(reported: list[str] | None, fmt: AddressFormat) -> list[str]:
    """Keep only what Claude reported that is one of the country's EXPECTED parts, under the configured label.

    Claude's list is advisory: anything that is not an expected part (a "helpful" part, a guess) never causes a
    follow-up question.
    """
    out: list[str] = []
    for item in reported or []:
        words = _tokens(str(item))
        if not words:
            continue
        for part in fmt.expected:
            if part not in out and words & _tokens(part):
                out.append(part)
                break
    return out[:MAX_MISSING_PARTS]


def join_parts(parts: list[str]) -> str:
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def apply_followup_rule(draft: Draft, missing: list[str]) -> None:
    """After the address text is saved: ask for missing parts (at most MAX_FOLLOWUPS times), else accept as given."""
    if missing and draft.address_followups < MAX_FOLLOWUPS:
        draft.address_followups += 1
        draft.address_missing = missing
    else:
        draft.address_missing = []


def no_answer_followup(draft: Draft) -> None:
    """The farmer replied to a follow-up without giving the missing part: ask again, or accept after the limit."""
    if draft.address_followups < MAX_FOLLOWUPS:
        draft.address_followups += 1
    else:
        draft.address_missing = []


def reset(draft: Draft) -> None:
    draft.full_address_text, draft.address_followups, draft.address_missing = None, 0, []
