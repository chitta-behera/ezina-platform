"""Checks Claude's drafted reply before it is sent. Failing replies are replaced by templates."""
from __future__ import annotations

import re

from app.schemas.conversation import Draft

MAX_REPLY_CHARS = 700

_VERIFICATION_CLAIM = re.compile(
    r"\b(you (are|have been|'re) (now )?(verified|approved|accepted)|(is|are|been) (now )?verified|"
    r"verification (is )?(complete|successful|approved)|account (is )?(now )?(verified|approved))\b",
    re.I,
)
_PROMISES = re.compile(
    r"\b(guarantee[sd]?|you will (definitely )?(earn|get paid|sell)|buyers will (buy|contact|pay)|"
    r"assured (sales|income|price)|we promise|promise (you )?(buyers|sales|income|a price)|"
    r"you will make money|guaranteed (income|sale|price))\b",
    re.I,
)
_SENSITIVE_ASK = re.compile(
    r"\b(national id|id number|passport number|bank (account|details)|account number|"
    r"password|\botp\b|one[- ]time (pin|password)|\bpin\b|credit card|card number)\b",
    re.I,
)
# Claude must never judge an ID or a selfie: the Ezina team does that.
_IDENTITY_JUDGEMENT = re.compile(
    r"\b(id|document|card|selfie|photo)\b.{0,30}\b(is|looks|seems|appears)\b.{0,15}"
    r"\b(genuine|real|fake|forged|valid|authentic|fraud\w*)\b"
    r"|\b(selfie|face|photo)\b.{0,30}\b(does not match|doesn't match|matches|match)\b",
    re.I,
)
_LONG_NUMBER = re.compile(r"\d(?:[ -]?\d){8,}")  # never repeat an ID number (or any long number)
_TYPED_COORDS_ASK = re.compile(r"\b(type|enter|write|send)\b.{0,30}\b(gps|coordinates|latitude|longitude)\b", re.I)

# crude "asking for X" detectors, used only against fields Python already holds
_ASKS = {
    "full_name": re.compile(r"\b(your (full )?name|may i know your name|what is your name)\b", re.I),
    "country": re.compile(r"\b(which|what) country\b", re.I),
    "full_address_text": re.compile(r"\b(what|which) is (the|your) (full |farm )*address\b|\bfull address\b", re.I),
    "crops": re.compile(r"\b(what|which) crops?\b", re.I),
    "cultivation_area": re.compile(r"\b(how much|how many) (land|acres|hectares)\b", re.I),
}


def check_reply(text: str, draft: Draft, *, status_facts_supplied: bool = False) -> tuple[bool, str]:
    """Return (ok, reason)."""
    if not text or not text.strip():
        return False, "empty"
    if len(text) > MAX_REPLY_CHARS:
        return False, "too_long"
    if text.count("\n") > 8:
        return False, "too_many_lines"
    if not status_facts_supplied and _VERIFICATION_CLAIM.search(text):
        return False, "claims_verification"
    if _PROMISES.search(text):
        return False, "promises_buyers_or_income"
    if _SENSITIVE_ASK.search(text):
        return False, "asks_sensitive_data"
    if _IDENTITY_JUDGEMENT.search(text):
        return False, "judges_identity_document"
    if _LONG_NUMBER.search(text):
        return False, "repeats_long_number"
    if _TYPED_COORDS_ASK.search(text):
        return False, "asks_typed_coordinates"
    if re.search(r"^\s*#{1,6}\s", text, re.M) or re.search(r"^\s*\|.*\|\s*$", text, re.M):
        return False, "markdown_headers_or_tables"
    collected = {
        "full_name": draft.full_name,
        "country": draft.country,
        # while follow-up questions for missing parts are open, the address is still being collected
        "full_address_text": None if draft.address_missing else draft.full_address_text,
        "crops": draft.crops,
        "cultivation_area": draft.cultivation_area,
    }
    for field_name, pattern in _ASKS.items():
        if collected.get(field_name) and pattern.search(text) and "?" in text:
            return False, f"asks_collected_{field_name}"
    return True, "ok"
