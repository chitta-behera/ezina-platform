"""Label-based extraction: find a printed field label and read the value on the same line or the line below.

Labels come from documents.yaml (case-insensitive; spaces, apostrophes and "/" are matched loosely so common OCR variants
still hit). Labels of relatives ("Father's Name", "S/O", ...) are *skip labels*: their value is never returned, and a
line that starts with a longer skip label than the wanted label is ignored.
"""
from __future__ import annotations

import re
from functools import lru_cache

from ezina_id_verify.config import Defaults, DocumentSpec
from ezina_id_verify.name.ocr import OcrLine
from ezina_id_verify.name.rules import Candidate, StopWords, clean_name, collapse, is_name_like, join_name, latin_only

_APOSTROPHES = "'’`´"
_LEADING_SEPARATORS = re.compile(r"^[\s:;.\-–—|/=]+")
_LOOKAHEAD_LINES = 3  # how far below a label the value may be (foreign-script lines in between are skipped)


@lru_cache(maxsize=512)
def _pattern(label: str) -> re.Pattern[str]:
    parts = []
    for word in label.split():
        chars = []
        for ch in word:
            if ch in _APOSTROPHES:
                chars.append(f"[{_APOSTROPHES}]?")
            elif ch == "/":
                chars.append(r"\s*/\s*")
            else:
                chars.append(re.escape(ch))
        parts.append("".join(chars))
    return re.compile(r"^\s*" + r"\s*".join(parts) + r"(?![A-Za-z])", re.IGNORECASE)


def _longest_match(text: str, labels: list[str]) -> re.Match[str] | None:
    best = None
    for label in labels:
        m = _pattern(label).match(text)
        if m and (best is None or m.end() > best.end()):
            best = m
    return best


class _Reader:
    def __init__(self, lines: list[OcrLine], targets: list[str], skips: list[str], stop: StopWords):
        self.lines = lines
        self.latin = [collapse(latin_only(l.text)) for l in lines]
        self.targets = targets
        self.skips = skips
        self.stop = stop
        self.known = targets + skips

    def _is_label_line(self, text: str) -> bool:
        return _longest_match(text, self.known) is not None

    def _value(self, text: str) -> str | None:
        value = clean_name(text, self.stop.titles)
        return value if value and is_name_like(value, self.stop, check_tokens=False) else None

    def _value_on_same_row(self, i: int) -> tuple[str, float] | None:
        """For a label alone on its OCR line: the value to its right on the same (straightened) row.

        A two-column card photographed at a slant is read column by column, so the line after a label may be the NEXT
        row's value (the relative's name). The rotated outlines tell where each line really is.
        """
        label = self.lines[i]
        if label.dy is None or label.dx is None:
            return None
        tolerance = 1.2 * (label.row_h or 0.03)
        best: tuple[float, int, str] | None = None
        for j, other in enumerate(self.lines):
            if j == i or other.dy is None or other.dx is None or other.dx <= label.dx:
                continue
            gap = abs(other.dy - label.dy)
            if gap > tolerance:
                continue
            text = _LEADING_SEPARATORS.sub("", self.latin[j])
            if not text or self._is_label_line(text):
                continue
            value = self._value(text)
            if value and (best is None or gap < best[0]):
                best = (gap, j, value)
        if best is None:
            return None
        return best[2], min(label.confidence, self.lines[best[1]].confidence)

    def read(self, labels: list[str]) -> tuple[str, float] | None:
        """(value, lowest OCR confidence) of the first occurrence of one of these labels, or None."""
        for i, text in enumerate(self.latin):
            text = _LEADING_SEPARATORS.sub("", text)
            hit = _longest_match(text, labels)
            if hit is None and "/" in text:
                # a bilingual label whose first-script half was read as noise ("film - / Given Name(s)"): use the part after "/"
                tail = _LEADING_SEPARATORS.sub("", text.split("/", 1)[1])
                tail_hit = _longest_match(tail, labels)
                if tail_hit is not None:
                    text, hit = tail, tail_hit
            if hit is None:
                continue
            skip = _longest_match(text, self.skips)
            if skip is not None and skip.end() >= hit.end():
                continue  # "Father's Name", "S/O ...": a relative, not the cardholder
            rest = _LEADING_SEPARATORS.sub("", text[hit.end():])
            if rest:
                value = self._value(rest)
                if value:
                    return value, self.lines[i].confidence
                continue
            same_row = self._value_on_same_row(i)
            if same_row is not None:
                return same_row
            for j in range(i + 1, min(len(self.lines), i + 1 + _LOOKAHEAD_LINES)):
                below = _LEADING_SEPARATORS.sub("", self.latin[j])
                if not below:
                    continue  # a line in another script (Hindi, Arabic, ...)
                if self._is_label_line(below):
                    break
                value = self._value(below)
                if value:
                    return value, min(self.lines[i].confidence, self.lines[j].confidence)
                if any(ch.isdigit() for ch in below):
                    continue  # a number from the next column (passport no., dates) read between the label and its value
                break
        return None


def extract_label_name(lines: list[OcrLine], spec: DocumentSpec, defaults: Defaults, stop: StopWords) -> Candidate | None:
    labels = spec.labels
    if labels is None:
        return None
    skips = list(defaults.skip_labels) + list(labels.skip)
    targets = list(labels.full_name) + list(labels.surname) + [v for group in labels.given_names for v in group]
    reader = _Reader(lines, targets, skips, stop)

    # separate surname + given-name fields: returned separately, full name = "given names surname"
    if labels.surname and labels.given_names:
        surname = reader.read(labels.surname)
        given_parts = [r for r in (reader.read(group) for group in labels.given_names) if r is not None]
        if surname is not None and given_parts:
            given = collapse(" ".join(v for v, _ in given_parts))
            confidence = min([surname[1]] + [c for _, c in given_parts])
            return Candidate("label", join_name(given, surname[0]), given_names=given, surname=surname[0],
                             ocr_confidence=confidence)
    # a single full-name label
    if labels.full_name:
        full = reader.read(labels.full_name)
        if full is not None:
            return Candidate("label", full[0], ocr_confidence=full[1])
    return None
