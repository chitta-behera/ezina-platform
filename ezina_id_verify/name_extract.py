"""extract_name: the cardholder's full name from an ID document image.

doc_type -> documents.yaml spec -> image checks -> OCR (Rekognition DetectText) -> the strategies configured for that
document type, in order (mrz, label, layout, llm) -> name rules -> NameResult.

Privacy: only the name is returned. ID numbers, dates of birth, addresses and OCR text are never returned, logged or
stored. "Name not found" is a result (found=false), not an exception.
"""
from __future__ import annotations

import asyncio
import logging
import time

from ezina_id_verify.config import get_settings, load_documents
from ezina_id_verify.images import prepare_image
from ezina_id_verify.models import NameResult, UnsupportedDocType
from ezina_id_verify.name.labels import extract_label_name
from ezina_id_verify.name.layout import extract_layout_name
from ezina_id_verify.name.llm import LlmUnavailable, extract_llm_name
from ezina_id_verify.name.mrz import extract_mrz_name
from ezina_id_verify.name.ocr import OcrProvider, RekognitionOcr
from ezina_id_verify.name.rules import Candidate, StopWords, apply_case, join_name

log = logging.getLogger("ezina_id_verify.name")

_BASE_CONFIDENCE = {"mrz": 0.95, "label": 0.85, "layout": 0.7, "llm": 0.6}
_LOW_OCR_CONFIDENCE = 80.0
MIN_OCR_LINES = 3  # fewer lines than this: the photo is probably unusable


def score(method: str, ocr_confidence: float | None, warnings: list[str]) -> float:
    """mrz 0.95; label 0.85 (-0.1 if the OCR line confidence < 80); layout 0.7; llm 0.6; -0.1 per warning; never below 0."""
    value = _BASE_CONFIDENCE[method]
    if method == "label" and ocr_confidence is not None and ocr_confidence < _LOW_OCR_CONFIDENCE:
        value -= 0.1
    value -= 0.1 * len(warnings)
    return round(max(0.0, min(1.0, value)), 2)


def _tokens(value: str | None) -> list[str]:
    return (value or "").upper().split()


def _confirm_with_labels(mrz: Candidate, printed: Candidate | None) -> Candidate | None:
    """An unclosed lone MRZ name is kept only when the printed name starts the same way (each MRZ word is the start of
    the printed word at that position, surname equal). The complete printed spelling is returned, flagged."""
    if printed is None or not printed.given_names or not printed.surname:
        return None
    m_given, p_given = _tokens(mrz.given_names), _tokens(printed.given_names)
    if _tokens(mrz.surname) != _tokens(printed.surname) or len(p_given) < len(m_given):
        return None
    if not all(p.startswith(m) for m, p in zip(m_given, p_given)):
        return None
    return Candidate("mrz", printed.full_name, printed.given_names, printed.surname,
                     warnings=("mrz_incomplete", "mrz_confirmed_by_label"), ocr_confidence=printed.ocr_confidence)


def _result(doc_type: str, candidate: Candidate, warnings: list[str], case: str) -> NameResult:
    given = apply_case(candidate.given_names, case)
    surname = apply_case(candidate.surname, case)
    full = join_name(given, surname) if (given or surname) else apply_case(candidate.full_name, case)
    return NameResult(
        doc_type=doc_type, found=True, full_name=full, given_names=given, surname=surname, method=candidate.method,
        confidence=score(candidate.method, candidate.ocr_confidence, warnings), warnings=warnings,
    )


async def extract_name(doc_type: str, id_image: bytes, *, ocr: OcrProvider | None = None) -> NameResult:
    """Read the cardholder's full name from an ID document image (JPEG or PNG bytes).

    Raises UnsupportedDocType, UnsupportedFile or RekognitionServiceError. `ocr` swaps the OCR provider (default:
    Rekognition DetectText).
    """
    started = time.perf_counter()
    docs = load_documents()
    resolved = docs.lookup(doc_type)
    if resolved is None:
        raise UnsupportedDocType(f"Unsupported document type {doc_type!r}. Supported: {', '.join(docs.doc_types)}")
    key, spec = resolved
    settings = get_settings()

    prepared = await asyncio.to_thread(prepare_image, id_image)
    lines = await (ocr or RekognitionOcr()).read_lines(prepared.data)
    stop = StopWords.build(docs.defaults, spec)

    candidate: Candidate | None = None
    warnings: list[str] = []
    for strategy in spec.strategies:
        if strategy == "mrz":
            candidate = extract_mrz_name(lines)
            if candidate is not None and "mrz_name_unclosed" in candidate.warnings:
                # only the first MRZ line, its name field not closed: it may be cut short, so the printed name must agree
                candidate = _confirm_with_labels(candidate, extract_label_name(lines, spec, docs.defaults, stop))
        elif strategy == "label":
            candidate = extract_label_name(lines, spec, docs.defaults, stop)
        elif strategy == "layout" and spec.layout:
            candidate = extract_layout_name(spec.layout, lines, stop)
        elif strategy == "llm" and settings.llm_fallback_enabled:
            try:
                candidate = await extract_llm_name(key, lines, settings, stop)
            except LlmUnavailable:
                warnings.append("llm_unavailable")
        if candidate is not None:
            break

    if candidate is not None:
        result = _result(key, candidate, warnings + list(candidate.warnings), settings.name_case)
    else:
        warnings.append("name_not_found")
        if len(lines) < MIN_OCR_LINES:
            warnings.append("low_image_quality")
        result = NameResult(doc_type=key, found=False, confidence=0.0, warnings=warnings)

    elapsed_ms = round((time.perf_counter() - started) * 1000)
    log.info(  # check type, doc_type, outcome, confidence and timing only: never a name, number or OCR text
        "name extraction doc_type=%s outcome=%s method=%s confidence=%.2f ocr_lines=%d ms=%d",
        key, "found" if result.found else "not_found", result.method, result.confidence, len(lines), elapsed_ms,
        extra={"check": "name", "doc_type": key, "outcome": "found" if result.found else "not_found",
               "method": result.method, "confidence": result.confidence, "ocr_lines": len(lines), "elapsed_ms": elapsed_ms},
    )
    return result
