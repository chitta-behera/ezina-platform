"""Shared image checks and preparation: JPEG and PNG only, detected from the bytes (never from a name or content type).

`prepare_image` validates the file, fixes EXIF rotation and, if needed, shrinks it under Rekognition's 5 MB byte limit
while keeping at least 1000 px on the longer side. Nothing is stored or logged.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Literal

from PIL import Image, ImageOps, UnidentifiedImageError

from ezina_id_verify.config import get_settings
from ezina_id_verify.models import UnsupportedFile

REKOGNITION_LIMIT_BYTES = 5_000_000  # Rekognition's limit is 5 MB (5,242,880); stay safely under it
MIN_LONGER_SIDE = 1000  # never shrink below this on the longer side (and never enlarge)
_JPEG_QUALITIES = (90, 80, 70, 55, 40)
_ORIENTATION_TAG = 0x0112

ONLY_JPEG_PNG = "Only JPEG and PNG images are supported"

ImageFormat = Literal["JPEG", "PNG"]


@dataclass(frozen=True)
class PreparedImage:
    data: bytes
    format: ImageFormat
    width: int
    height: int


def detect_format(data: bytes) -> ImageFormat | None:
    """JPEG or PNG from the magic bytes, else None."""
    if data[:3] == b"\xff\xd8\xff":
        return "JPEG"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "PNG"
    return None


def _encode(img: Image.Image, fmt: ImageFormat, quality: int = 92) -> bytes:
    buf = io.BytesIO()
    if fmt == "PNG":
        img.save(buf, format="PNG", optimize=True)
    else:
        rgb = img
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            rgba = img.convert("RGBA")
            rgb = Image.new("RGB", rgba.size, (255, 255, 255))
            rgb.paste(rgba, mask=rgba.getchannel("A"))
        elif img.mode != "RGB":
            rgb = img.convert("RGB")
        rgb.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _shrink_to_limit(img: Image.Image) -> bytes:
    """A JPEG under the byte limit: lower the quality, then the size, never below MIN_LONGER_SIDE on the long side."""
    longer = max(img.size)
    floor = min(1.0, MIN_LONGER_SIDE / longer)
    scale = 1.0
    while True:
        resized = img if scale >= 1.0 else img.resize(
            (max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS
        )
        for quality in _JPEG_QUALITIES:
            out = _encode(resized, "JPEG", quality)
            if len(out) <= REKOGNITION_LIMIT_BYTES:
                return out
        if scale <= floor:
            raise UnsupportedFile("The image is too large to process, even after compression. Please send a smaller photo.")
        scale = max(floor, scale * 0.8)


def prepare_image(data: bytes, *, max_upload_mb: float | None = None) -> PreparedImage:
    """Validate and prepare one image for Rekognition. Raises UnsupportedFile with a clear message."""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise UnsupportedFile("The image must be given as bytes.")
    data = bytes(data)
    if not data:
        raise UnsupportedFile("The file is empty.")
    limit_mb = max_upload_mb if max_upload_mb is not None else get_settings().max_upload_mb
    if len(data) > limit_mb * 1024 * 1024:
        raise UnsupportedFile(f"The file is larger than {limit_mb:g} MB.")
    fmt = detect_format(data)
    if fmt is None:
        extra = " PDF files are not accepted; send a photo of the document." if data[:5] == b"%PDF-" else ""
        raise UnsupportedFile(f"{ONLY_JPEG_PNG}.{extra}")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError, MemoryError):
        raise UnsupportedFile("The image file could not be read.") from None
    # a JPEG from some phones is an MPO container; the magic bytes are still JPEG
    if not (img.format == fmt or (img.format == "MPO" and fmt == "JPEG")):
        raise UnsupportedFile("The image file could not be read.")

    needs_rotation = img.getexif().get(_ORIENTATION_TAG, 1) not in (0, 1)
    oversize = len(data) > REKOGNITION_LIMIT_BYTES
    if not needs_rotation and not oversize:
        return PreparedImage(data, fmt, *img.size)

    if needs_rotation:
        img = ImageOps.exif_transpose(img)
    if fmt == "PNG" and not oversize:
        out, out_fmt = _encode(img, "PNG"), "PNG"
        if len(out) > REKOGNITION_LIMIT_BYTES:  # rotating cannot grow it much, but be safe
            out, out_fmt = _shrink_to_limit(img), "JPEG"
    else:
        out = _encode(img, "JPEG", 92)
        out_fmt = "JPEG"
        if len(out) > REKOGNITION_LIMIT_BYTES:
            out = _shrink_to_limit(img)
    with Image.open(io.BytesIO(out)) as result:
        return PreparedImage(out, out_fmt, *result.size)
