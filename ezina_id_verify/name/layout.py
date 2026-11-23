"""Layout-based extraction, for documents whose name has no printed label.

* aadhaar_above_dob: the cardholder's English name is the closest name-like line ABOVE the DOB / Year of Birth / date
  line. Hindi and other regional-script lines, headers, gender words and relative lines (S/O, D/O, W/O, C/O, Father,
  Husband) are skipped. Fallback: the first name-like line on the card.
* pan_header: old-format PAN has no "Name" label. The first name-like line below the "INCOME TAX DEPARTMENT" /
  "GOVT. OF INDIA" header is the cardholder; the next one is the father's name and is never returned.
* first_name_line: the first name-like line after skipping known header words (generic_id, best effort).
"""
from __future__ import annotations

import re

from ezina_id_verify.name.ocr import OcrLine
from ezina_id_verify.name.rules import Candidate, StopWords, clean_name, collapse, is_name_like, latin_only

_DOB = re.compile(
    r"\b(?:dob|d\.\s?o\.\s?b\.?|date\s+of\s+birth|year\s+of\s+birth|yob)\b|\b\d{1,2}\s*[/\-.]\s*\d{1,2}\s*[/\-.]\s*\d{4}\b",
    re.IGNORECASE,
)
_PAN_HEADERS = ("income tax department", "govt of india", "government of india")


def _candidate(text: str, stop: StopWords) -> str | None:
    name = clean_name(text, stop.titles)
    return name if name and is_name_like(name, stop) else None


def _phrase_key(text: str) -> str:
    return " ".join(re.findall(r"[a-z]+", text.lower()))


def _first_name_line(lines: list[OcrLine], stop: StopWords, start: int = 0) -> Candidate | None:
    for line in lines[start:]:
        name = _candidate(line.text, stop)
        if name:
            return Candidate("layout", name, ocr_confidence=line.confidence)
    return None


def _aadhaar_above_dob(lines: list[OcrLine], stop: StopWords) -> Candidate | None:
    for i, line in enumerate(lines):
        latin = collapse(latin_only(line.text))
        m = _DOB.search(latin)
        if m is None:
            continue
        before = latin[: m.start()]  # a name on the same line as the DOB marker
        name = _candidate(before, stop) if before.strip(" :-|") else None
        if name:
            return Candidate("layout", name, ocr_confidence=line.confidence)
        for j in range(i - 1, -1, -1):  # the closest name-like line above
            name = _candidate(lines[j].text, stop)
            if name:
                return Candidate("layout", name, ocr_confidence=lines[j].confidence)
        break
    return _first_name_line(lines, stop)


def _pan_header(lines: list[OcrLine], stop: StopWords) -> Candidate | None:
    last_header = -1
    for i, line in enumerate(lines):
        key = _phrase_key(latin_only(line.text))
        if any(h in key for h in _PAN_HEADERS):
            last_header = i
    if last_header < 0:
        return None
    return _first_name_line(lines, stop, start=last_header + 1)


def extract_layout_name(kind: str, lines: list[OcrLine], stop: StopWords) -> Candidate | None:
    if kind == "aadhaar_above_dob":
        return _aadhaar_above_dob(lines, stop)
    if kind == "pan_header":
        return _pan_header(lines, stop)
    if kind == "first_name_line":
        return _first_name_line(lines, stop)
    return None
