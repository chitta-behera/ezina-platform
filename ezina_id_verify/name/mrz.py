"""Name from a machine-readable zone (ICAO Doc 9303). The most reliable source, so it is preferred when present.

* TD3 (passports): 2 lines x 44 characters. Line 1 = document type (2 chars: "P" + a letter or "<") + issuing state
  (3 chars, which may contain "<", e.g. "D<<") + the name from the 6th character.
* TD1 (ID cards): 3 lines x 30 characters, the name is the whole of line 3.
* TD2 (ID cards): 2 lines x 36 characters, the name is on line 1 from the 6th character.
Name field: SURNAME<<GIVEN<NAMES, "<" is a space, an empty surname is valid.
Only the name is read; the other MRZ fields (number, dates) are never looked at.
"""
from __future__ import annotations

import re

from ezina_id_verify.name.ocr import OcrLine
from ezina_id_verify.name.rules import Candidate, join_name

_OCR_FILLER = str.maketrans({"«": "<<", "‹": "<", "〈": "<", "＜": "<", "‚": "<"})
_DIGIT_FOR_LETTER = str.maketrans({"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z"})
_NOT_MRZ = re.compile(r"[^A-Z0-9<]")
_LETTERS = re.compile(r"^[A-Z ]*$")


def normalise_line(text: str) -> str:
    """Common OCR slips fixed: "«" becomes "<<", spaces and stray characters are removed."""
    t = text.translate(_OCR_FILLER).upper()
    return _NOT_MRZ.sub("", re.sub(r"\s+", "", t))


def _looks_like_mrz(norm: str) -> bool:
    return len(norm) >= 26 and norm.count("<") >= 2


def parse_name_field(field: str) -> tuple[str | None, str | None] | None:
    """(given_names, surname) from "SURNAME<<GIVEN<NAMES<<<<", or None if it does not look like a name."""
    field = re.sub(r"<[<KC]{3,}$", "", field)  # padding "<<<<" that OCR read as "<<KKK"
    field = re.sub(r"[KC]{4,}$", "", field)  # padding read as letters only
    field = field.rstrip("<").translate(_DIGIT_FOR_LETTER)  # digits cannot be in a name
    if not field:
        return None
    if "<<" in field:
        surname_part, given_part = field.split("<<", 1)
    else:
        surname_part, given_part = field, ""  # only a surname
    surname = re.sub(r"\s+", " ", surname_part.replace("<", " ")).strip()
    given = re.sub(r"\s+", " ", given_part.replace("<", " ")).strip()
    if not (surname or given):
        return None
    if not (_LETTERS.match(surname) and _LETTERS.match(given)):
        return None
    return (given or None), (surname or None)  # an empty surname is valid


def _candidate(field: str) -> Candidate | None:
    parsed = parse_name_field(field)
    if parsed is None:
        return None
    given, surname = parsed
    return Candidate("mrz", join_name(given, surname), given_names=given, surname=surname)


def _between(n: int, low: int, high: int) -> bool:
    return low <= n <= high


_LONE_TD3 = re.compile(r"^P[A-Z<][A-Z<]{3}")


def _lone_passport_line(lines: list[OcrLine]) -> Candidate | None:
    """A photo that shows only the first MRZ line (the second is cropped or unreadable).

    Accepted only when the line is unmistakably a passport line 1 ("P<" + issuing state) and the name field is closed by
    "<<" (the end-of-name filler), so a name cut off by the image edge is never returned. Flagged "mrz_incomplete".
    """
    for line in lines:
        norm = normalise_line(line.text)
        if len(norm) < 20 or not _LONE_TD3.match(norm) or not norm.rstrip("K").endswith("<<"):
            continue
        found = _candidate(norm[5:])
        if found is not None and found.given_names:
            return Candidate("mrz", found.full_name, found.given_names, found.surname, warnings=("mrz_incomplete",))
    return None


def extract_mrz_name(lines: list[OcrLine]) -> Candidate | None:
    return _full_mrz_name(lines) or _lone_passport_line(lines)


def _full_mrz_name(lines: list[OcrLine]) -> Candidate | None:
    runs: list[list[str]] = []  # consecutive MRZ-looking lines
    current: list[str] = []
    for line in lines:
        norm = normalise_line(line.text)
        if _looks_like_mrz(norm):
            current.append(norm)
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    for run in runs:
        for i, line in enumerate(run):
            nxt = run[i + 1] if i + 1 < len(run) else ""
            third = run[i + 2] if i + 2 < len(run) else ""
            if line[:1] == "P" and _between(len(line), 40, 48) and _between(len(nxt), 40, 48):
                found = _candidate(line[5:])  # TD3: after the 2-char type and the 3-char issuing state
            elif line[:1] in ("I", "A", "C") and _between(len(line), 28, 32) and _between(len(nxt), 28, 32) \
                    and _between(len(third), 28, 32):
                found = _candidate(third)  # TD1: the whole of line 3
            elif line[:1] in ("I", "A", "C") and _between(len(line), 34, 38) and _between(len(nxt), 34, 38):
                found = _candidate(line[5:])  # TD2
            else:
                continue
            if found is not None:
                return found
    return None
