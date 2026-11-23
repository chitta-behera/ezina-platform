"""Name comparison for the ID name check. Pure Python, no I/O, unit-tested.

Compares the name the farmer gave with the name read from the ID. Tolerant of word order, middle names, initials
("J. Mokoena" vs "John Mokoena"), titles, accents and small spelling differences. The result is advisory input for the
operations team: it never verifies a farmer.
"""
from __future__ import annotations

import re
import unicodedata

from rapidfuzz import fuzz

from app.enums import NameCheckStatus

TITLES = {
    "mr", "mrs", "ms", "miss", "mx", "dr", "prof", "sir", "madam", "mister", "late", "shri", "sri", "smt",
    "kumari", "kum", "shrimati", "rra", "mma", "mme",
}


def normalise(name: str | None) -> str:
    """Lowercase, no accents, no punctuation, no titles, single spaces."""
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)  # "J.", "O'Neil", "Mokoena-Dube" -> separate tokens
    return " ".join(t for t in text.split() if t not in TITLES)


def _expand_initials(a: list[str], b: list[str]) -> list[str]:
    """Replace each single-letter token of `a` by an unused token of `b` that starts with that letter."""
    used: set[int] = set()
    out: list[str] = []
    for tok in a:
        if len(tok) == 1:
            for i, other in enumerate(b):
                if i not in used and len(other) > 1 and other.startswith(tok):
                    used.add(i)
                    tok = other
                    break
        out.append(tok)
    return out


def score(given: str | None, on_id: str | None) -> float:
    """0-100 similarity of two names (0 when either has nothing to compare)."""
    a, b = normalise(given).split(), normalise(on_id).split()
    if not a or not b:
        return 0.0
    a2, b2 = _expand_initials(a, b), _expand_initials(b, a)
    sa_, sb_ = " ".join(a2), " ".join(b2)
    best = fuzz.token_sort_ratio(sa_, sb_)
    # token_set_ratio ignores extra words (middle names), but a lone given name must not match any longer name
    if min(len(set(a2)), len(set(b2))) >= 2:
        best = max(best, fuzz.token_set_ratio(sa_, sb_))
    return round(float(best), 2)


def compare(given: str | None, on_id: str | None, *, threshold: float = 90, partial: float = 75) -> tuple[NameCheckStatus, float]:
    """(status, score): MATCHED >= threshold, PARTIAL >= partial, else MISMATCH; NOT_FOUND if the ID gave no name."""
    if not normalise(on_id):
        return NameCheckStatus.NOT_FOUND, 0.0
    s = score(given, on_id)
    if s >= threshold:
        return NameCheckStatus.MATCHED, s
    if s >= partial:
        return NameCheckStatus.PARTIAL, s
    return NameCheckStatus.MISMATCH, s
