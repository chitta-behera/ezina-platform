"""Client for the external face-verification API (selfie vs the photo on the ID document).

The result is advisory input for the operations team. Python interprets it (`classify`), the farmer is never shown a
score, and nothing here verifies anyone. Logging is limited to status codes, timings and the result status: never an
image and never a score.
"""
from __future__ import annotations

import asyncio
import io
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import Settings
from app.enums import FaceCheckStatus

log = logging.getLogger("ezina.faceverify")
_FILE_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


class FaceVerifyError(Exception):
    """The API could not be used. `reason` is safe to log (no images, no scores)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class FaceResult:
    """The fields kept from the API response. Unknown fields are ignored; missing ones stay None."""

    verified: bool | None = None
    distance: float | None = None
    threshold: float | None = None
    confidence_band: str | None = None
    liveness_passed: bool | None = None
    face_found_id: bool | None = None
    face_found_selfie: bool | None = None
    model: str | None = None
    detector: str | None = None
    processing_ms: float | None = None
    error: str | None = None
    warnings: list[str] = field(default_factory=list)


def _bool(v: Any) -> bool | None:
    return v if isinstance(v, bool) else None


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _text(v: Any, limit: int = 500) -> str | None:
    return str(v)[:limit] if v not in (None, "") else None


def parse_result(payload: Any) -> FaceResult:
    """Tolerant parse: extra fields are ignored, missing optional ones become None. A non-object is unparseable."""
    if not isinstance(payload, dict):
        raise FaceVerifyError("unparseable_response")
    warnings = payload.get("warnings")
    error = _text(payload.get("error"))
    issues = payload.get("issues")  # the API's own quality gate: e.g. ["selfie is too blurry (sharpness 18.4 < 60.0)"]
    if error is not None and isinstance(issues, list) and issues:
        error = f"{error}: {'; '.join(str(i)[:120] for i in issues[:4])}"[:500]  # for operations; never shown to the farmer
    return FaceResult(
        verified=_bool(payload.get("verified")), distance=_num(payload.get("distance")),
        threshold=_num(payload.get("threshold")), confidence_band=_text(payload.get("confidence_band"), 100),
        liveness_passed=_bool(payload.get("liveness_passed")), face_found_id=_bool(payload.get("face_found_id")),
        face_found_selfie=_bool(payload.get("face_found_selfie")), model=_text(payload.get("model"), 100),
        detector=_text(payload.get("detector"), 100), processing_ms=_num(payload.get("processing_ms")),
        error=error,
        warnings=[str(w)[:200] for w in warnings][:20] if isinstance(warnings, list) else [],
    )


_RESULT_KEYS = ("verified", "error", "face_found_id", "face_found_selfie")


def _looks_like_result(payload: Any) -> bool:
    return isinstance(payload, dict) and any(k in payload for k in _RESULT_KEYS)


def _validation_summary(payload: Any) -> str:
    """For a real "your request is invalid" 4xx (e.g. {"detail": [{"loc": [...], "msg": "..."}]}): which fields, no values."""
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if not isinstance(detail, list):
        return ""
    parts = []
    for item in detail[:3]:
        if isinstance(item, dict):
            loc = ".".join(str(x) for x in item.get("loc", []) if isinstance(x, (str, int)))
            parts.append(f"{loc}: {str(item.get('msg', ''))[:60]}".strip(": "))
    return "; ".join(p for p in parts if p)[:200]


def classify(r: FaceResult) -> FaceCheckStatus:
    """Python decides, in this order: error, no face (ID), no face (selfie), liveness, verified, not verified.

    One refinement: this API reports "no face found" as an `error` together with face_found_id / face_found_selfie
    false. That is a definite face result (the farmer can fix it), not a failure of the API, so an explicit "no face"
    flag wins over the error text. Any other `error` is ERROR.
    """
    explicit_no_face = r.face_found_id is False or r.face_found_selfie is False
    if r.error is not None and not explicit_no_face:
        return FaceCheckStatus.ERROR
    if r.face_found_id is False:
        return FaceCheckStatus.NO_FACE_ID
    if r.face_found_selfie is False:
        return FaceCheckStatus.NO_FACE_SELFIE
    if r.liveness_passed is False:
        return FaceCheckStatus.LIVENESS_FAILED
    if r.verified is True:
        return FaceCheckStatus.MATCHED
    if r.verified is False:
        return FaceCheckStatus.MISMATCH
    return FaceCheckStatus.ERROR  # no verdict at all: cannot be used


def pdf_first_page_png(data: bytes) -> bytes:
    """Render the first page of a PDF as a PNG (an ID front stored as PDF). Raises on any failure."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    try:
        image = pdf[0].render(scale=2).to_pil().convert("RGB")
    finally:
        pdf.close()
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _blurry_images(error: str | None) -> tuple[bool, bool]:
    """(id_blurry, selfie_blurry) from the API's quality-gate rejection ("... ID photo is too blurry (...)"), else (False, False)."""
    text = (error or "").lower()
    if "image quality check failed" not in text:
        return False, False
    return "id photo is too blurry" in text, "selfie is too blurry" in text


def sharpen_jpeg(data: bytes) -> bytes:
    """A mildly sharpened JPEG copy (unsharp mask r=2, 250%). WhatsApp's recompression softens photos below the API's
    sharpness gate; this is deliberately mild (a stronger setting made the API's liveness check fail). Raises on a bad image."""
    from PIL import Image, ImageFilter

    with Image.open(io.BytesIO(data)) as im:
        out = im.convert("RGB").filter(ImageFilter.UnsharpMask(radius=2, percent=250, threshold=0))
    buf = io.BytesIO()
    out.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


class FaceVerifyService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.s = settings
        self._client = client
        self._owns_client = client is None

    @property
    def available(self) -> bool:
        return bool(self.s.face_verify_enabled and self.s.face_verify_api_url)

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient()
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        key = self.s.face_verify_api_key.get_secret_value()
        if not key:
            return {}
        header = self.s.face_verify_api_key_header or "Authorization"
        return {header: f"Bearer {key}" if header.lower() == "authorization" else key}

    async def verify(self, *, id_image: bytes, id_mime: str, selfie_image: bytes, selfie_mime: str) -> FaceResult:
        """Verify, and if the API's quality gate says a photo is too blurry, retry ONCE with a mildly sharpened copy of
        just that photo (WhatsApp recompresses photos below the gate). The stored images are never changed."""
        
        result = await self._call(id_image=id_image, id_mime=id_mime, selfie_image=selfie_image, selfie_mime=selfie_mime)
        id_blurry, selfie_blurry = _blurry_images(result.error)
        if not (self.s.face_verify_sharpen_retry and (id_blurry or selfie_blurry)):
            return result
        try:
            if id_blurry:
                id_image, id_mime = sharpen_jpeg(id_image), "image/jpeg"
            if selfie_blurry:
                selfie_image, selfie_mime = sharpen_jpeg(selfie_image), "image/jpeg"
        except Exception as e:  # not an image Pillow can read: keep the first result
            log.info("face verify sharpen failed", extra={"error": type(e).__name__})
            return result
        log.info("face verify sharpen retry", extra={"id": id_blurry, "selfie": selfie_blurry})
        return await self._call(id_image=id_image, id_mime=id_mime, selfie_image=selfie_image, selfie_mime=selfie_mime)

    async def _call(self, *, id_image: bytes, id_mime: str, selfie_image: bytes, selfie_mime: str) -> FaceResult:
        """POST both images (multipart: id_image + selfie_image) and return the parsed result.

        Retries timeouts, connection errors and 5xx with exponential backoff; a 4xx or an unparseable body is not
        retried. Raises FaceVerifyError when the API cannot be used.
        """
        id_name = f"id.{_FILE_EXT.get(id_mime, 'bin')}"
        selfie_name = f"selfie.{_FILE_EXT.get(selfie_mime, 'bin')}"
        attempts = 1 + max(0, self.s.face_verify_max_retries)
        reason = "error"
        for n in range(attempts):
            started = time.monotonic()
            status: int | None = None
            try:
                resp = await self._http().post(
                    self.s.face_verify_api_url,
                    headers=self._headers(),
                    files={"id_image": (id_name, id_image, id_mime), "selfie_image": (selfie_name, selfie_image, selfie_mime)},
                    timeout=self.s.face_verify_timeout_seconds,
                )
            except (httpx.TimeoutException, httpx.TransportError) as e:  # timeouts and connection errors
                reason = type(e).__name__
            else:
                status = resp.status_code
                if status < 300:
                    log.info("face verify call", extra={"status": status, "seconds": round(time.monotonic() - started, 2),
                                                        "attempt": n + 1})
                    try:
                        return parse_result(resp.json())
                    except ValueError as e:
                        raise FaceVerifyError("unparseable_response") from e
                reason = f"http_{status}"
                if status < 500:  # a client error will not fix itself: no retry
                    log.info("face verify call", extra={"status": status, "attempt": n + 1})
                    try:
                        body = resp.json()
                    except ValueError:
                        body = None
                    if _looks_like_result(body):  # this API answers "no face found" with a 4xx AND a result body
                        return parse_result(body)
                    summary = _validation_summary(body)
                    raise FaceVerifyError(f"{reason} {summary}".strip())
            log.info("face verify call", extra={"status": status, "error": reason,
                                                "seconds": round(time.monotonic() - started, 2), "attempt": n + 1})
            if n < attempts - 1:
                await asyncio.sleep(self.s.face_verify_retry_base_delay * (2 ** n))
        raise FaceVerifyError(reason)
