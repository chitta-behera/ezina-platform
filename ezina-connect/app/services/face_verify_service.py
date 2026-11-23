"""Selfie face check: the selfie compared with the photo on the ID document, by the ezina_id_verify package (AWS Rekognition).

The package is called in-process (no HTTP API) and retries AWS errors itself, so nothing is retried here. The result is
advisory input for the operations team. Python interprets it (`classify`), the farmer is never shown a score, and nothing
here verifies anyone. Logging is limited to statuses and timings: never an image and never face data.
"""
from __future__ import annotations

import io
import logging
import time
from dataclasses import dataclass, field

from ezina_id_verify import FaceMatchResult, match_face

from app.config import Settings
from app.enums import FaceCheckStatus

log = logging.getLogger("ezina.faceverify")


class FaceVerifyError(Exception):
    """The check could not be run (AWS failure, unusable image, ...). `reason` is safe to log (no images, no scores)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class FaceResult:
    """The fields kept from the package's FaceMatchResult. Missing ones stay None."""

    verified: bool | None = None
    similarity: float | None = None  # 0-100, higher is better; for operations only, never shown to the farmer
    threshold: float | None = None
    confidence_band: str | None = None  # "match" | "possible_match" | "no_match"
    liveness_passed: bool | None = None  # always None from Rekognition: the WhatsApp finger challenge is the liveness check
    face_found_id: bool | None = None
    face_found_selfie: bool | None = None
    selfie_quality_ok: bool | None = None
    model: str | None = None
    processing_ms: float | None = None
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    distance: float | None = None  # legacy (the old HTTP API): never set now; the column stays for old rows
    detector: str | None = None  # legacy: same


def classify(r: FaceResult) -> FaceCheckStatus:
    """Python decides, in this order: error, no face (ID), no face (selfie), verified, not verified.

    `liveness_passed` is not consulted: Rekognition never reports it (None), so this result never produces
    LIVENESS_FAILED. Quality warnings ("eyes_closed", ...) never override a MATCHED result. A "possible_match" is not
    verified, so it is a MISMATCH like "no_match".
    """
    if r.error is not None:
        return FaceCheckStatus.ERROR
    if r.face_found_id is False:
        return FaceCheckStatus.NO_FACE_ID
    if r.face_found_selfie is False:
        return FaceCheckStatus.NO_FACE_SELFIE
    if r.verified is True:
        return FaceCheckStatus.MATCHED
    if r.verified is False:
        return FaceCheckStatus.MISMATCH
    return FaceCheckStatus.ERROR  # no verdict at all: cannot be used


def pdf_first_page_png(data: bytes) -> bytes:
    """Render the first page of a PDF as a PNG (an ID front stored as PDF before PDFs were refused). Raises on any failure."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    try:
        image = pdf[0].render(scale=2).to_pil().convert("RGB")
    finally:
        pdf.close()
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _from_package(r: FaceMatchResult) -> FaceResult:
    return FaceResult(
        verified=r.verified, similarity=r.similarity, threshold=r.threshold, confidence_band=r.confidence_band,
        liveness_passed=r.liveness_passed, face_found_id=r.face_found_id, face_found_selfie=r.face_found_selfie,
        selfie_quality_ok=r.selfie_quality_ok, model=r.model, processing_ms=r.processing_ms,
        error=str(r.error)[:500] if r.error else None, warnings=[str(w)[:200] for w in (r.warnings or [])][:20],
    )


class FaceVerifyService:
    def __init__(self, settings: Settings):
        self.s = settings

    @property
    def available(self) -> bool:
        return bool(self.s.face_verify_enabled)

    async def aclose(self) -> None:  # nothing to close: no HTTP client any more (kept for the container's shutdown)
        return None

    async def verify(self, *, id_image: bytes, id_mime: str, selfie_image: bytes, selfie_mime: str) -> FaceResult:
        """Compare the two photos. The mime types are not needed (the package detects JPEG/PNG from the bytes).

        Raises FaceVerifyError when the check cannot be run (AWS failure, not a JPEG/PNG, ...); the caller turns that
        into the ERROR status. Never raises anything else.
        """
        started = time.monotonic()
        try:
            result = _from_package(await match_face(id_image, selfie_image))
        except Exception as e:  # RekognitionServiceError, UnsupportedFile, or a package configuration problem
            reason = str(getattr(e, "code", None) or type(e).__name__)[:100]
            log.info("face verify call", extra={"error": reason, "seconds": round(time.monotonic() - started, 2)})
            raise FaceVerifyError(reason) from e
        log.info("face verify call", extra={"seconds": round(time.monotonic() - started, 2),
                                            "has_error": result.error is not None, "warnings": len(result.warnings)})
        return result
