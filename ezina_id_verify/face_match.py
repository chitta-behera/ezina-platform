"""match_face: does the face on an ID document match the selfie?

1. DetectFaces on the selfie: no face stops here (CompareFaces is not called); several faces -> warning, the largest is
   used; quality problems (blur, darkness, sunglasses, closed eyes) become warnings.
2. CompareFaces (source = the ID image, target = the selfie) with SimilarityThreshold=0, so the score is always returned;
   the threshold is applied here, in Python. Rekognition uses the largest face of the source image, which handles
   passports with a second, smaller "ghost" photo.

liveness_passed is always None: Rekognition Face Liveness needs an in-app video session and cannot run on a WhatsApp
photo (liveness is handled by ezina-connect's challenge). Face images and coordinates are never returned or logged.

The two face_found_* flags are False only when Rekognition positively reported no usable face in that image. When an
image was not examined (the selfie had no face, so the ID was never compared) its flag stays True, so a client cannot
mistake "not examined" for "no face".
"""
from __future__ import annotations

import asyncio
import logging
import time

from ezina_id_verify.config import Settings, get_settings
from ezina_id_verify.images import PreparedImage, prepare_image
from ezina_id_verify.models import FaceMatchResult, UnsupportedFile
from ezina_id_verify.rekognition import RekognitionClientError, acall

log = logging.getLogger("ezina_id_verify.face")

MODEL = "aws-rekognition-compare-faces"
_IMAGE_REJECTED_CODES = {"InvalidParameterException", "InvalidImageFormatException", "ImageTooLargeException"}


async def _prepare(data: bytes, label: str) -> PreparedImage:
    try:
        return await asyncio.to_thread(prepare_image, data)
    except UnsupportedFile as e:
        raise UnsupportedFile(f"{label}: {e}") from None


def _area(face: dict) -> float:
    box = face.get("BoundingBox", {})
    return float(box.get("Width", 0.0)) * float(box.get("Height", 0.0))


def _quality_warnings(face: dict, settings: Settings) -> list[str]:
    warnings = []
    quality = face.get("Quality", {})
    if float(quality.get("Sharpness", 100.0)) < settings.face_min_sharpness:
        warnings.append("selfie_blurry")
    if float(quality.get("Brightness", 100.0)) < settings.face_min_brightness:
        warnings.append("selfie_dark")
    if face.get("Sunglasses", {}).get("Value") is True:
        warnings.append("sunglasses")
    if face.get("EyesOpen", {}).get("Value") is False:
        warnings.append("eyes_closed")
    return warnings


def _band(similarity: float, settings: Settings) -> str:
    if similarity >= settings.face_match_threshold:
        return "match"
    if similarity >= settings.face_possible_match_threshold:
        return "possible_match"
    return "no_match"


def _is_no_face_message(message: str) -> bool:
    m = message.lower()
    return "no face" in m or "no faces" in m or "faces in the image" in m


async def match_face(id_image: bytes, selfie_image: bytes) -> FaceMatchResult:
    """Compare the face on the ID image with the selfie (JPEG or PNG bytes).

    Raises UnsupportedFile or RekognitionServiceError. "No face" and "faces do not match" are results, not exceptions.
    """
    settings = get_settings()
    id_img = await _prepare(id_image, "ID image")
    selfie_img = await _prepare(selfie_image, "Selfie image")

    started = time.perf_counter()
    warnings: list[str] = []

    def result(**fields) -> FaceMatchResult:
        ms = round((time.perf_counter() - started) * 1000, 1)
        out = FaceMatchResult(
            threshold=settings.face_match_threshold, processing_ms=ms, warnings=warnings,
            **{"verified": False, "face_found_id": True, "face_found_selfie": True, **fields},
        )
        log.info(  # check type, outcome, similarity and timing only: no images, no coordinates
            "face match outcome=%s similarity=%s band=%s ms=%.1f",
            _outcome(out), out.similarity, out.confidence_band, ms,
            extra={"check": "face", "outcome": _outcome(out), "similarity": out.similarity,
                   "confidence_band": out.confidence_band, "elapsed_ms": ms},
        )
        return out

    # 1. the selfie
    try:
        detected = await acall("detect_faces", Image={"Bytes": selfie_img.data}, Attributes=["ALL"])
    except RekognitionClientError as e:
        if e.code in _IMAGE_REJECTED_CODES:
            return result(face_found_selfie=False, error="selfie_image_rejected")
        raise
    faces = detected.get("FaceDetails", [])
    if not faces:
        return result(face_found_selfie=False)
    if len(faces) > 1:
        warnings.append("multiple_faces_selfie")
    quality = _quality_warnings(max(faces, key=_area), settings)
    warnings.extend(quality)
    quality_ok = not quality

    # 2. the comparison (source = the ID, target = the selfie)
    try:
        compared = await acall(
            "compare_faces", SourceImage={"Bytes": id_img.data}, TargetImage={"Bytes": selfie_img.data},
            SimilarityThreshold=0, QualityFilter="NONE",
        )
    except RekognitionClientError as e:
        if e.code == "InvalidParameterException" and _is_no_face_message(e.aws_message):
            selfie_side = "target" in e.aws_message.lower()
            return result(face_found_id=selfie_side, face_found_selfie=not selfie_side, selfie_quality_ok=quality_ok)
        if e.code in _IMAGE_REJECTED_CODES:
            return result(face_found_id=False, selfie_quality_ok=quality_ok, error="id_image_rejected")
        raise

    source_face = compared.get("SourceImageFace") or {}
    if not source_face:
        return result(face_found_id=False, selfie_quality_ok=quality_ok)
    if float(source_face.get("BoundingBox", {}).get("Width", 1.0)) < settings.face_id_min_width:
        warnings.append("small_face_id")

    matches = compared.get("FaceMatches", [])
    similarity = round(max((float(m.get("Similarity", 0.0)) for m in matches), default=0.0), 2)
    return result(
        verified=similarity >= settings.face_match_threshold, similarity=similarity,
        confidence_band=_band(similarity, settings), selfie_quality_ok=quality_ok,
    )


def _outcome(r: FaceMatchResult) -> str:
    if r.error:
        return "error"
    if not r.face_found_selfie:
        return "no_face_selfie"
    if not r.face_found_id:
        return "no_face_id"
    return "match" if r.verified else (r.confidence_band or "no_match")
