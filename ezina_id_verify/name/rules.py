"""Name validation and cleanup shared by every extraction strategy.

A "name-like" line has only Latin letters (accents allowed), spaces, dots, apostrophes and hyphens, 1-6 words, no digits,
and is not a known label, header, gender or country word (the stop lists come from documents.yaml).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Literal

from ezina_id_verify.config import Defaults, DocumentSpec

MAX_WORDS = 6
_ALLOWED_PUNCT = frozenset(".'’-")
_TRIM_CHARS = " \t\r\n:;,.|/\\-–—_=*~"
_WORD_RE = re.compile(r"[a-z]+")
# "S/O Ramesh", "W/O", "Father Ramesh", "Son of ..." : a relative, never the cardholder
RELATION_PREFIX = re.compile(
    r"^\s*(?:[sdwc]\s*[/\\.]\s*o\b|s[\s/|\\Il1.\-_:]{0,3}d[\s/|\\Il1.\-_:]{0,3}w\b|father\b|husband\b|mother\b|wife\s+of\b|son\s+of\b|daughter\s+of\b|care\s+of\b)",
    re.IGNORECASE,
)

Method = Literal["mrz", "label", "layout", "llm"]


@dataclass
class Candidate:
    """A name found by one strategy, before scoring."""

    method: Method
    full_name: str
    given_names: str | None = None
    surname: str | None = None
    warnings: tuple[str, ...] = ()  # raised by the strategy itself, e.g. "mrz_incomplete"
    ocr_confidence: float | None = None  # lowest Rekognition line confidence (0-100) behind it, if OCR lines were used


@dataclass(frozen=True)
class StopWords:
    tokens: frozenset[str] = field(default_factory=frozenset)  # single words that are never part of a name (layout)
    phrases: tuple[str, ...] = ()  # header phrases that are never a name (all strategies)
    titles: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def build(cls, defaults: Defaults, spec: DocumentSpec | None = None) -> "StopWords":
        tokens = {_word_key(w) for w in defaults.stop_words}
        phrases = {_phrase_key(p) for p in defaults.stop_phrases}
        if spec is not None:
            tokens |= {_word_key(w) for w in spec.stop_words}
            phrases |= {_phrase_key(p) for p in spec.stop_phrases}
        return cls(frozenset(t for t in tokens if t), tuple(sorted(p for p in phrases if p)),
                   frozenset(_word_key(t) for t in defaults.titles))


def _word_key(word: str) -> str:
    return "".join(_WORD_RE.findall(word.lower()))


def _phrase_key(phrase: str) -> str:
    return " ".join(_WORD_RE.findall(phrase.lower()))


def is_latin_letter(ch: str) -> bool:
    return ch.isalpha() and unicodedata.name(ch, "").startswith("LATIN")


def latin_only(text: str) -> str:
    """Drop letters of other scripts (Devanagari, Arabic, ...), keeping Latin letters, digits and punctuation."""
    out = []
    for ch in unicodedata.normalize("NFC", text):
        if unicodedata.category(ch) in ("Mn", "Mc", "Me"):
            continue  # combining marks that did not compose into a Latin letter (e.g. Devanagari vowel signs)
        out.append(" " if (ch.isalpha() and not is_latin_letter(ch)) else ch)
    return "".join(out)


def collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def clean_name(raw: str, titles: frozenset[str] = frozenset()) -> str:
    """Latin part of a line, with surrounding punctuation and leading titles (Mr, Shri, Smt, ...) removed."""
    text = collapse(latin_only(raw)).strip(_TRIM_CHARS)
    words = text.split(" ") if text else []
    while len(words) > 1 and _word_key(words[0]) in titles:
        words.pop(0)
    if len(words) == 1 and _word_key(words[0]) in titles:
        return ""
    return collapse(" ".join(words)).strip(_TRIM_CHARS)


def is_name_like(text: str, stop: StopWords | None = None, *, check_tokens: bool = True) -> bool:
    """See the module docstring. `check_tokens=False` skips the single-word stop list: used for the value that follows an
    explicit label, where a real name such as "Given" or "Africa" must not be rejected (headers still are)."""
    text = collapse(text)
    if not text or RELATION_PREFIX.match(text):
        return False
    for ch in text:
        if not (is_latin_letter(ch) or ch == " " or ch in _ALLOWED_PUNCT):
            return False  # digits, slashes, other scripts, symbols
    words = text.split(" ")
    if not 1 <= len(words) <= MAX_WORDS:
        return False
    if words[-1].lower() == "of":
        return False  # a label fragment ("S/D/W of"), never the end of a name
    if any(not any(is_latin_letter(c) for c in w) for w in words):
        return False
    if max(sum(is_latin_letter(c) for c in w) for w in words) < 2:
        return False
    if stop is not None:
        key = " " + _phrase_key(text) + " "
        if any(f" {p} " in key for p in stop.phrases):
            return False
        if check_tokens and any(_word_key(w) in stop.tokens for w in words):
            return False
    return True


def apply_case(name: str | None, mode: str) -> str | None:
    if not name:
        return name
    if mode == "upper":
        return name.upper()
    if mode == "title":
        return re.sub(r"[^\W\d_]+", lambda m: m.group().capitalize(), name.lower())
    return name


def join_name(given_names: str | None, surname: str | None) -> str:
    """Full name as "given names surname"."""
    return collapse(" ".join(p for p in (given_names, surname) if p))
