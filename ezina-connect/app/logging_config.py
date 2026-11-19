"""Structured JSON logging with personal-data masking."""
from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime

_PHONE = re.compile(r"(?<![\w.])\+?\d{9,15}(?![\w.])")
_BEARER = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+")
_TOKENISH = re.compile(r"(?i)(access_token|api[_-]?key|authorization|secret)(['\"]?\s*[:=]\s*['\"]?)[^\s,'\"}]+")
_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


def mask_phone(value: str | None) -> str:
    """+26771234567 -> +26*******567"""
    if not value:
        return ""
    s = str(value)
    if len(s) <= 6:
        return "***"
    return s[:3] + "*" * (len(s) - 6) + s[-3:]


def scrub(text: str) -> str:
    text = _BEARER.sub(r"\1***", text)
    text = _TOKENISH.sub(r"\1\2***", text)
    return _PHONE.sub(lambda m: mask_phone(m.group(0)), text)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": scrub(record.getMessage()),
        }
        for k, v in record.__dict__.items():
            if k not in _RESERVED and not k.startswith("_"):
                data[k] = scrub(v) if isinstance(v, str) else v
        if record.exc_info:
            data["exc"] = scrub(self.formatException(record.exc_info))
        return json.dumps(data, default=str, ensure_ascii=False)


def setup_logging(level: str = "INFO", production: bool = False) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter()
        if production
        else _DevFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)  # httpx logs full URLs


class _DevFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = super().format(record)
        extras = {k: v for k, v in record.__dict__.items() if k not in _RESERVED and not k.startswith("_")}
        if extras:
            out += " " + " ".join(f"{k}={v}" for k, v in extras.items())
        return scrub(out)
