"""Result models and exceptions: the whole public contract of the package.

"Name not found", "no face found" and "faces do not match" are results, never exceptions.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class IdVerifyError(Exception):
    """Base class of the exceptions this package raises."""


class UnsupportedDocType(IdVerifyError, ValueError):
    """The doc_type is not configured in documents.yaml."""


class UnsupportedFile(IdVerifyError, ValueError):
    """Not a JPEG/PNG image, too large, empty or unreadable. The message is safe to show to a caller."""


class RekognitionServiceError(IdVerifyError):
    """AWS Rekognition failed (after retries, or with an error that retrying cannot fix)."""

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code


class NameResult(BaseModel):
    """The cardholder's name read from an ID document. No ID numbers, dates, addresses or OCR text."""

    doc_type: str
    found: bool
    full_name: str | None = None  # e.g. "CHITTA RANJAN BEHERA"
    name: str | None = None  # same as full_name, for clients that read "name"
    given_names: str | None = None  # None if the document does not separate them
    surname: str | None = None  # None if the document does not separate them
    method: Literal["mrz", "label", "layout", "llm"] | None = None
    confidence: float = 0.0  # 0.0 - 1.0
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _name_mirrors_full_name(self) -> "NameResult":
        self.name = self.full_name
        return self


class FaceMatchResult(BaseModel):
    """The outcome of comparing the face on an ID document with a selfie. Field names match ezina-connect's face check."""

    verified: bool  # similarity >= FACE_MATCH_THRESHOLD
    similarity: float | None = None  # 0-100, from Rekognition
    threshold: float  # FACE_MATCH_THRESHOLD used
    confidence_band: Literal["match", "possible_match", "no_match"] | None = None
    face_found_id: bool
    face_found_selfie: bool
    # Always None: Rekognition Face Liveness needs an in-app video session and cannot run on a WhatsApp photo.
    liveness_passed: bool | None = None
    selfie_quality_ok: bool | None = None  # from DetectFaces quality checks
    model: str = "aws-rekognition-compare-faces"
    processing_ms: float = 0.0
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)
