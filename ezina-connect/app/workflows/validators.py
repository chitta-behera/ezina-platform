"""Python-side validation of every value before it is saved. Claude's output is never trusted."""
from __future__ import annotations

import re

import pycountry


class ValidationFailure(Exception):
    def __init__(self, field: str, message: str, example: str):
        super().__init__(message)
        self.field = field
        self.message = message
        self.example = example


_COUNTRY_ALIASES = {
    "uk": "GB", "england": "GB", "britain": "GB", "usa": "US", "america": "US", "uae": "AE",
    "south korea": "KR", "russia": "RU", "tanzania": "TZ", "ivory coast": "CI",
}


def validate_name(value: str) -> str:
    v = re.sub(r"\s+", " ", (value or "").strip())
    if len(v) < 2 or len(v) > 100 or not re.search(r"[^\W\d_]", v):
        raise ValidationFailure("full_name", "invalid name", "John Mokoena")
    if sum(c.isdigit() for c in v) > 2 or re.search(r"[<>{}\[\]/\\@]", v):
        raise ValidationFailure("full_name", "invalid name", "John Mokoena")
    return v


def validate_country(value: str) -> str:
    v = (value or "").strip()
    if not v:
        raise ValidationFailure("country", "empty country", "Botswana")
    alias = _COUNTRY_ALIASES.get(v.lower())
    if alias:
        return alias
    if len(v) == 2 and v.isalpha():
        c = pycountry.countries.get(alpha_2=v.upper())
        if c:
            return c.alpha_2
    try:
        return pycountry.countries.lookup(v).alpha_2
    except LookupError:
        # No fuzzy matching on purpose: a typo must never silently become a different country.
        raise ValidationFailure("country", "unknown country", "Botswana or India") from None


def country_name(code: str | None) -> str:
    if not code:
        return ""
    c = pycountry.countries.get(alpha_2=code)
    return getattr(c, "common_name", None) or c.name if c else code


def validate_place(field: str, value: str) -> str:
    v = re.sub(r"\s+", " ", (value or "").strip())
    if len(v) < 2 or len(v) > 150 or not re.search(r"[^\W\d_]", v):
        raise ValidationFailure(field, f"invalid {field}", "Gaborone" if field != "district" else "South East")
    return v


def validate_optional_text(field: str, value: str, max_len: int = 300) -> str:
    v = re.sub(r"\s+", " ", (value or "").strip())
    if not v or len(v) > max_len:
        raise ValidationFailure(field, f"invalid {field}", "Green Acres Farm")
    return v


_CROP_ALIASES = {
    "corn": "maize", "mealie": "maize", "mealies": "maize", "maize": "maize",
    "tomatoes": "tomato", "potatoes": "potato", "groundnuts": "groundnut", "peanuts": "groundnut",
    "peanut": "groundnut", "chili": "chilli", "chilies": "chilli", "chillies": "chilli",
    "onions": "onion", "cabbages": "cabbage", "beans": "bean", "mangoes": "mango",
    "bananas": "banana", "cassava": "cassava", "sorghum": "sorghum", "millet": "millet",
}


def normalize_crop(raw: str) -> str:
    v = re.sub(r"\s+", " ", raw.strip().lower())
    if v in _CROP_ALIASES:
        return _CROP_ALIASES[v]
    if v.endswith("ies") and len(v) > 4:
        return v[:-3] + "y"
    if v.endswith("s") and not v.endswith("ss") and len(v) > 3:
        return v[:-1]
    return v


def validate_crops(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in values or []:
        for part in re.split(r",|;|\band\b|\+|&", item):
            p = re.sub(r"\s+", " ", part.strip())
            if not p:
                continue
            if len(p) > 60 or not re.search(r"[^\W\d_]", p):
                raise ValidationFailure("crops", "invalid crop", "maize, tomatoes")
            key = normalize_crop(p)
            if key not in seen:
                seen.add(key)
                out.append(p)
    if not out:
        raise ValidationFailure("crops", "no crops", "maize, tomatoes")
    if len(out) > 15:
        raise ValidationFailure("crops", "too many crops", "maize, tomatoes")
    return out


_UNITS = {
    "acre": "acre", "acres": "acre", "ac": "acre",
    "hectare": "hectare", "hectares": "hectare", "ha": "hectare", "hect": "hectare",
    "sqm": "square_metre", "m2": "square_metre", "m²": "square_metre",
    "square metre": "square_metre", "square metres": "square_metre",
    "square meter": "square_metre", "square meters": "square_metre",
}
_TO_HECTARES = {"acre": 0.40468564224, "hectare": 1.0, "square_metre": 0.0001}
UNIT_LABEL = {"acre": "acres", "hectare": "hectares", "square_metre": "square metres"}


def validate_area(value: float | str | None, unit: str | None) -> tuple[float, str, float]:
    """Return (value, canonical_unit, hectares)."""
    example = "5 acres or 2 hectares"
    try:
        num = float(str(value).replace(",", "")) if value is not None else None
    except ValueError:
        num = None
    if num is None or num <= 0:
        raise ValidationFailure("cultivation_area", "area must be positive", example)
    canon = _UNITS.get((unit or "").strip().lower().rstrip("."))
    if canon is None:
        raise ValidationFailure("area_unit", "unsupported unit", example)
    hectares = round(num * _TO_HECTARES[canon], 4)
    if hectares < 0.001 or hectares > 20000:
        raise ValidationFailure("cultivation_area", "implausible area", example)
    return num, canon, hectares


_AREA_RE = re.compile(r"(\d[\d,]*\.?\d*)\s*([a-zA-Z²][a-zA-Z²\s]*)?")


def parse_area_text(text: str) -> tuple[float | None, str | None]:
    m = _AREA_RE.search(text or "")
    if not m:
        return None, None
    try:
        num = float(m.group(1).replace(",", ""))
    except ValueError:
        return None, None
    unit = (m.group(2) or "").strip().lower() or None
    return num, unit


def validate_lat_lon(lat: float | None, lon: float | None) -> tuple[float, float]:
    if lat is None or lon is None or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        raise ValidationFailure("location", "invalid coordinates", "use WhatsApp Attach > Location")
    return float(lat), float(lon)


def validate_language(value: str, supported: dict[str, str]) -> str:
    v = (value or "").strip().lower()
    if v in supported:
        return v
    for code, name in supported.items():
        if v == name.lower():
            return code
    raise ValidationFailure("preferred_language", "unsupported language", ", ".join(supported.values()))


_COORD_RE = re.compile(r"-?\d{1,3}\.\d{3,}\s*[,;]?\s*-?\d{1,3}\.\d{3,}")


def looks_like_coordinates(text: str) -> bool:
    return bool(_COORD_RE.search(text or ""))
