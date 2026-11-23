"""Ezina ID verification with AWS Rekognition: two independent checks.

    from ezina_id_verify import extract_name, match_face

    name = await extract_name("passport", id_bytes)        # NameResult
    face = await match_face(id_bytes, selfie_bytes)        # FaceMatchResult

Only JPEG and PNG images are supported (the type is detected from the bytes). "Name not found", "no face found" and
"faces do not match" are returned in the result; exceptions are only UnsupportedDocType, UnsupportedFile and
RekognitionServiceError.
"""
from ezina_id_verify.face_match import match_face
from ezina_id_verify.models import (
    FaceMatchResult,
    NameResult,
    RekognitionServiceError,
    UnsupportedDocType,
    UnsupportedFile,
)
from ezina_id_verify.name_extract import extract_name

__version__ = "0.1.0"

__all__ = [
    "extract_name",
    "NameResult",
    "match_face",
    "FaceMatchResult",
    "UnsupportedDocType",
    "UnsupportedFile",
    "RekognitionServiceError",
]
