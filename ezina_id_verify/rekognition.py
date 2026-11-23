"""One shared boto3 Rekognition client, with retry/backoff, callable from async code.

boto3 is synchronous, so every call runs in a worker thread (asyncio.to_thread) and never blocks the event loop.
Throttling, 5xx and network errors are retried with exponential backoff; when the retries are used up (or the error
cannot be fixed by retrying) RekognitionServiceError is raised. Nothing here logs request or response content.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from ezina_id_verify.config import get_settings
from ezina_id_verify.models import RekognitionServiceError

log = logging.getLogger("ezina_id_verify.rekognition")

_RETRYABLE_CODES = {
    "ThrottlingException", "ThrottledException", "ProvisionedThroughputExceededException", "RequestLimitExceeded",
    "InternalServerError", "ServiceUnavailable", "ServiceUnavailableException", "SlowDown", "RequestTimeout",
}


class RekognitionClientError(RekognitionServiceError):
    """A Rekognition error that retrying cannot fix (bad image, no access, ...). `code` is the AWS error code."""

    def __init__(self, message: str, code: str | None, aws_message: str = ""):
        super().__init__(message, code)
        self.aws_message = aws_message  # AWS's own description; never contains image data


_client: Any = None


def get_client() -> Any:
    global _client
    if _client is None:
        s = get_settings()
        _client = boto3.client(
            "rekognition",
            region_name=s.aws_region,
            # we do our own retries (below), so botocore makes a single attempt
            config=Config(retries={"max_attempts": 1, "mode": "standard"}, connect_timeout=10, read_timeout=30),
        )
    return _client


def set_client(client: Any | None) -> None:
    """Use this client from now on (None: build a new one on next use). Mainly for tests."""
    global _client
    _client = client


def _is_retryable(error: Exception) -> tuple[bool, str]:
    if isinstance(error, ClientError):
        code = error.response.get("Error", {}).get("Code", "Unknown")
        status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
        return (code in _RETRYABLE_CODES or status >= 500), code
    return True, type(error).__name__  # connection / timeout errors raised by botocore


def call(operation: str, **kwargs: Any) -> dict:
    """Synchronous Rekognition call with retries. Raises RekognitionServiceError / RekognitionClientError."""
    s = get_settings()
    attempts = 1 + s.aws_max_retries
    for n in range(attempts):
        started = time.monotonic()
        try:
            response = getattr(get_client(), operation)(**kwargs)
            log.debug("rekognition call", extra={"operation": operation, "attempt": n + 1,
                                                 "elapsed_ms": round((time.monotonic() - started) * 1000)})
            return response
        except (ClientError, BotoCoreError) as e:
            retryable, code = _is_retryable(e)
            log.info("rekognition error", extra={"operation": operation, "attempt": n + 1, "code": code, "retryable": retryable})
            if not retryable:
                aws_message = e.response.get("Error", {}).get("Message", "") if isinstance(e, ClientError) else str(e)
                raise RekognitionClientError(f"AWS Rekognition {operation} was rejected: {code}", code, aws_message) from e
            if n == attempts - 1:
                raise RekognitionServiceError(
                    f"AWS Rekognition {operation} failed after {attempts} attempts: {code}", code
                ) from e
            time.sleep(s.aws_retry_base_delay * (2**n) + random.uniform(0, s.aws_retry_base_delay / 2))
    raise RekognitionServiceError(f"AWS Rekognition {operation} failed")  # unreachable


async def acall(operation: str, **kwargs: Any) -> dict:
    """`call` in a worker thread, for async callers."""
    return await asyncio.to_thread(call, operation, **kwargs)
