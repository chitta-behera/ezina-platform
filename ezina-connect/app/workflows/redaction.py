"""Redacts things that look like ID numbers from farmer text before it is stored or sent anywhere.

Ezina never asks for ID numbers. If a farmer types one anyway, it is replaced at ingest so the raw value never
reaches the messages table, the conversation draft, logs or the Claude prompt. Heuristic: it cannot catch every
national format (e.g. short alphanumeric passport numbers); the rule is "8+ digits" or an Indian PAN pattern.
"""
from __future__ import annotations

import re

REDACTED = "[ID number removed]"
_DIGITS = re.compile(r"(?<![\w])\d(?:[ -]?\d){7,}(?![\w])")  # 8+ digits, optional single space/hyphen between
_PAN = re.compile(r"\b[A-Za-z]{5}\d{4}[A-Za-z]\b")


def redact_id_numbers(text: str | None) -> tuple[str | None, bool]:
    """Return (text with ID-like numbers replaced, whether anything was redacted)."""
    if not text:
        return text, False
    out, n1 = _DIGITS.subn(REDACTED, text)
    out, n2 = _PAN.subn(REDACTED, out)
    return out, bool(n1 or n2)
