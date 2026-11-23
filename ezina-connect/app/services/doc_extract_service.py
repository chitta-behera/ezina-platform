"""Client for the external document-extraction API (ID document -> the name printed on it).

Only the name is read from the response; every other field (ID number, date of birth, address, ...) is discarded
unseen. Logging is limited to status codes and timings: never the image, the extracted name or any ID number.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from app.config import Settings

log = logging.getLogger("ezina.docextract")
_FILE_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "application/pdf": "pdf"}


class DocExtractError(Exception):
    """The API could not be used. `reason` is safe to log (no names, no numbers)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def read_name(payload: Any, name_fields: list[str]) -> str | None:
    """Join the configured name fields (dot paths allowed, e.g. "data.name") with a space, in order.

    Missing, empty or non-text fields are skipped. Returns None when nothing is left. Reads nothing else.
    """
    parts: list[str] = []
    for path in name_fields:
        node: Any = payload
        for key in path.split("."):
            node = node.get(key) if isinstance(node, dict) else None
            if node is None:
                break
        if isinstance(node, str) and node.strip():
            parts.append(" ".join(node.split()))
    return " ".join(parts) or None


class DocExtractService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.s = settings
        self._client = client
        self._owns_client = client is None

    @property
    def available(self) -> bool:
        return bool(self.s.doc_extract_enabled and self.s.doc_extract_api_url)

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient()
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        key = self.s.doc_extract_api_key.get_secret_value()
        if not key:
            return {}
        header = self.s.doc_extract_api_key_header or "Authorization"
        return {header: f"Bearer {key}" if header.lower() == "authorization" else key}

    async def extract_name(self, *, doc_type: str, name_fields: list[str], data: bytes, mime: str) -> str | None:
        """POST the image (multipart: doc_type + file) and return only the name; None when the ID has no name field.

        Retries timeouts, connection errors and 5xx with exponential backoff; a 4xx or an unparseable body is not
        retried. Raises DocExtractError when the API cannot be used.
        """
        filename = f"id.{_FILE_EXT.get(mime, 'bin')}"
        attempts = 1 + max(0, self.s.doc_extract_max_retries)
        reason = "error"
        for n in range(attempts):
            started = time.monotonic()
            try:
                resp = await self._http().post(
                    self.s.doc_extract_api_url,
                    headers=self._headers(),
                    data={"doc_type": doc_type},
                    files={"file": (filename, data, mime)},
                    timeout=self.s.doc_extract_timeout_seconds,
                )
            except (httpx.TimeoutException, httpx.TransportError) as e:  # timeouts and connection errors
                reason = type(e).__name__
                status: int | None = None
            else:
                status = resp.status_code
                log.info("doc extract call", extra={"status": status, "seconds": round(time.monotonic() - started, 2),
                                                    "attempt": n + 1})
                if status < 300:
                    try:
                        payload = resp.json()
                    except ValueError as e:
                        raise DocExtractError("unparseable_response") from e
                    return read_name(payload, name_fields)
                if status < 500:
                    raise DocExtractError(f"http_{status}")  # a client error will not fix itself: no retry
                reason = f"http_{status}"
            if status is None:
                log.info("doc extract call", extra={"status": None, "error": reason,
                                                    "seconds": round(time.monotonic() - started, 2), "attempt": n + 1})
            if n < attempts - 1:
                await asyncio.sleep(self.s.doc_extract_retry_base_delay * (2 ** n))
        raise DocExtractError(reason)
