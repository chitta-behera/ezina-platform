"""OCR behind an interface, so Amazon Textract (or anything else) can be added without changing the extractors.

The Rekognition implementation uses DetectText LINE detections only, ordered top-to-bottom and then left-to-right.
Lines that sit on the same row (a label and its value are often separate detections) are grouped before ordering.
OCR text is never logged or stored.
"""
from __future__ import annotations

import io
import math
from dataclasses import dataclass, replace
from typing import Protocol

from ezina_id_verify.rekognition import acall


@dataclass(frozen=True)
class OcrLine:
    text: str
    confidence: float  # 0-100
    top: float  # BoundingBox, fraction of the image height
    left: float  # BoundingBox, fraction of the image width
    height: float = 0.0
    # Straightened position (units of the image height), set only when the OCR gave rotated outlines and the image size:
    # a tilted photo of a two-column card then still lines every value up with its own label.
    dx: float | None = None
    dy: float | None = None
    row_h: float = 0.0  # the text height, same units


class OcrProvider(Protocol):
    async def read_lines(self, image: bytes) -> list[OcrLine]:
        """The text lines of a JPEG/PNG image, in reading order."""
        ...


def reading_order(lines: list[OcrLine]) -> list[OcrLine]:
    """Top-to-bottom by BoundingBox.Top, then left-to-right; detections on the same row are kept together."""
    rows: list[list[OcrLine]] = []
    centre = 0.0
    for line in sorted(lines, key=lambda l: (l.top, l.left)):
        c = line.top + line.height / 2
        if rows:
            first = rows[-1][0]
            tolerance = 0.5 * min(first.height or 0.02, line.height or 0.02)
            if abs(c - centre) <= tolerance:
                rows[-1].append(line)
                continue
        rows.append([line])
        centre = c
    return [line for row in rows for line in sorted(row, key=lambda l: l.left)]


_MIN_LINES_FOR_ANGLE = 3


def _polygon(det: dict, width: int, height: int) -> list[tuple[float, float]] | None:
    pts = det.get("Geometry", {}).get("Polygon") or []
    if len(pts) != 4:
        return None
    try:
        return [(float(p["X"]) * width, float(p["Y"]) * height) for p in pts]
    except (KeyError, TypeError, ValueError):
        return None


def _straighten(lines: list[OcrLine], polys: list[list[tuple[float, float]] | None], size: tuple[int, int]) -> list[OcrLine]:
    """Add dx/dy: each line's centre rotated back by the page's tilt (the median angle of the text baselines)."""
    if len(lines) < _MIN_LINES_FOR_ANGLE or any(p is None for p in polys):
        return lines
    angles = sorted(math.atan2(p[1][1] - p[0][1], p[1][0] - p[0][0]) for p in polys if p)
    tilt = angles[len(angles) // 2]
    if abs(math.degrees(tilt)) > 45:  # sideways or upside down: not a tilt this can undo
        return lines
    cos, sin = math.cos(tilt), math.sin(tilt)
    out = []
    for line, poly in zip(lines, polys):
        cx = sum(q[0] for q in poly) / 4
        cy = sum(q[1] for q in poly) / 4
        text_h = math.hypot(poly[2][0] - poly[1][0], poly[2][1] - poly[1][1])
        out.append(replace(line, dx=(cx * cos + cy * sin) / size[1], dy=(-cx * sin + cy * cos) / size[1],
                           row_h=text_h / size[1]))
    return out


def lines_from_response(response: dict, size: tuple[int, int] | None = None) -> list[OcrLine]:
    """`size` = (width, height) in pixels; with it, lines also carry their straightened position (dx, dy)."""
    lines: list[OcrLine] = []
    polys: list[list[tuple[float, float]] | None] = []
    for det in response.get("TextDetections", []):
        if det.get("Type") != "LINE":
            continue
        text = (det.get("DetectedText") or "").strip()
        if not text:
            continue
        box = det.get("Geometry", {}).get("BoundingBox", {})
        lines.append(OcrLine(
            text=text, confidence=float(det.get("Confidence", 0.0)),
            top=float(box.get("Top", 0.0)), left=float(box.get("Left", 0.0)), height=float(box.get("Height", 0.0)),
        ))
        polys.append(_polygon(det, *size) if size else None)
    if size:
        lines = _straighten(lines, polys, size)
    return reading_order(lines)


def _image_size(image: bytes) -> tuple[int, int] | None:
    try:
        from PIL import Image

        with Image.open(io.BytesIO(image)) as im:
            return im.size
    except Exception:  # noqa: BLE001 - geometry is a refinement; the plain OCR lines still work without it
        return None


class RekognitionOcr:
    """DetectText on the image bytes (JPEG/PNG, under 5 MB: see images.prepare_image)."""

    async def read_lines(self, image: bytes) -> list[OcrLine]:
        return lines_from_response(await acall("detect_text", Image={"Bytes": image}), _image_size(image))
