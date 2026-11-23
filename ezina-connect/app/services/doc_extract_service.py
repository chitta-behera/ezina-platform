"""ID name check: the name printed on an ID photo, read by the ezina_id_verify package (AWS Rekognition).

The package is called in-process (no HTTP API). It returns only the name; ID numbers, dates of birth, addresses and raw
OCR text never reach this code. Logging is limited to the check status, the method, the confidence and timings: never
the image, the extracted name or any OCR text. The package already retries AWS errors, so nothing is retried here.

Mapping of the package's outcomes to this app's name-check statuses (every exception is caught here):
    found, with a name          -> PENDING   (the caller compares it with the farmer's name: MATCHED / PARTIAL / MISMATCH)
    not found                   -> NOT_FOUND (the farmer is asked for a clearer photo)
    UnsupportedFile             -> NOT_FOUND, `unsupported_file` set (the farmer is asked for a clear JPEG/PNG photo)
    UnsupportedDocType          -> SKIPPED   (the flow continues)
    RekognitionServiceError     -> ERROR     (the farmer is not blocked; flagged for operations review)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from ezina_id_verify import (
    NameResult,
    RekognitionServiceError,
    UnsupportedDocType,
    UnsupportedFile,
    extract_name,
)

from app.config import Settings
from app.enums import NameCheckStatus
from app.workflows import identity_flow

log = logging.getLogger("ezina.docextract")


@dataclass
class NameExtraction:
    """What the name check kept. `name` is sensitive: never logged, never sent to Claude."""

    status: NameCheckStatus  # PENDING (name found, waiting for the comparison) | NOT_FOUND | SKIPPED | ERROR
    name: str | None = None
    method: str | None = None  # "mrz" | "label" | "layout" | "llm"
    confidence: float | None = None  # 0-1
    reason: str | None = None  # safe to log: no names, no OCR text
    unsupported_file: bool = False  # the image was not a usable JPEG/PNG: ask for a new photo


class DocExtractService:
    def __init__(self, settings: Settings):
        self.s = settings

    @property
    def available(self) -> bool:
        return bool(self.s.doc_extract_enabled)

    async def aclose(self) -> None:  # nothing to close: no HTTP client any more (kept for the container's shutdown)
        return None

    @staticmethod
    def verify_doc_type(id_document_type: str | None) -> str | None:
        """The ezina_id_verify doc_type for an ID type (id_documents.yaml `extraction:`), or None: not checked (SKIPPED)."""
        spec = identity_flow.extraction_for(id_document_type)
        return spec.verify_doc_type if spec else None

    async def extract_name(self, *, id_document_type: str | None, data: bytes) -> NameExtraction:
        """Read the name from the stored ID front. Never raises: every failure becomes a status (see the module docs)."""
        doc_type = self.verify_doc_type(id_document_type)
        if not self.available or doc_type is None:
            return NameExtraction(NameCheckStatus.SKIPPED, reason="off" if not self.available else "no_doc_type")
        started = time.monotonic()
        try:
            result: NameResult = await extract_name(doc_type, data)
        except UnsupportedDocType:
            return self._done(NameExtraction(NameCheckStatus.SKIPPED, reason="unsupported_doc_type"), doc_type, started)
        except UnsupportedFile:
            return self._done(
                NameExtraction(NameCheckStatus.NOT_FOUND, reason="unsupported_file", unsupported_file=True), doc_type, started)
        except RekognitionServiceError as e:
            return self._done(
                NameExtraction(NameCheckStatus.ERROR, reason=str(getattr(e, "code", None) or "rekognition_error")[:100]),
                doc_type, started)
        except Exception as e:  # e.g. a bad documents.yaml in the package: never block the farmer
            return self._done(NameExtraction(NameCheckStatus.ERROR, reason=type(e).__name__), doc_type, started)
        if result.doc_type != doc_type:
            log.warning("name check doc_type differs from the one passed",
                        extra={"passed": doc_type, "returned": result.doc_type})
        name = " ".join((result.full_name or "").split())
        if not result.found or not name:
            return self._done(NameExtraction(NameCheckStatus.NOT_FOUND, reason="name_not_found",
                                             method=result.method, confidence=result.confidence), doc_type, started)
        return self._done(
            NameExtraction(NameCheckStatus.PENDING, name=name, method=result.method, confidence=result.confidence),
            doc_type, started)

    @staticmethod
    def _done(out: NameExtraction, doc_type: str, started: float) -> NameExtraction:
        log.info("name check call", extra={
            "doc_type": doc_type, "status": out.status.value, "method": out.method, "confidence": out.confidence,
            "reason": out.reason, "seconds": round(time.monotonic() - started, 2)})
        return out
