"""Shared test helpers. AWS is never called: a real boto3 Rekognition client is wrapped in botocore's Stubber, which also
validates every saved fixture against the real response shape."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path

import boto3
import pytest
from botocore import xform_name
from botocore.config import Config
from botocore.stub import Stubber
from make_fixtures import detect_text as build_detect_text
from PIL import Image

from ezina_id_verify import rekognition
from ezina_id_verify.config import Settings, reset_documents_cache, set_settings
from ezina_id_verify.name import llm

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def make_settings(**overrides) -> Settings:
    base = dict(_env_file=None, aws_retry_base_delay=0.0)  # no .env, no waiting between retries
    return Settings(**{**base, **overrides})


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch):
    """Default settings for every test (nothing read from the environment or a .env file); LLM client reset."""
    for var in list(os.environ):
        if var.startswith(("AWS_", "FACE_", "ID_VERIFY_", "LLM_", "NAME_CASE", "MAX_UPLOAD", "CLAUDE_", "ANTHROPIC_")):
            monkeypatch.delenv(var, raising=False)
    set_settings(make_settings())
    reset_documents_cache()
    llm.set_client(None)
    yield
    set_settings(None)
    reset_documents_cache()
    rekognition.set_client(None)
    llm.set_client(None)


class Aws:
    """Queue Rekognition responses (saved fixtures or errors) and see what the code sent."""

    def __init__(self):
        self.client = boto3.client(
            "rekognition", region_name="us-east-1", aws_access_key_id="test", aws_secret_access_key="test",
            config=Config(retries={"max_attempts": 1}),
        )
        self.stubber = Stubber(self.client)
        self.calls: list[tuple[str, dict]] = []
        self.client.meta.events.register(
            "before-parameter-build.rekognition.*", lambda params, model, **kw: self.calls.append((xform_name(model.name), dict(params)))
        )
        self.stubber.activate()
        rekognition.set_client(self.client)

    def _add(self, operation: str, response) -> "Aws":
        self.stubber.add_response(operation, load(response) if isinstance(response, str) else response)
        return self

    def detect_text(self, fixture) -> "Aws":
        """A saved fixture name, or a list of text lines (built into a DetectText response)."""
        return self._add("detect_text", build_detect_text(fixture) if isinstance(fixture, list) else fixture)

    def detect_faces(self, fixture) -> "Aws":
        return self._add("detect_faces", fixture)

    def compare_faces(self, fixture) -> "Aws":
        return self._add("compare_faces", fixture)

    def error(self, operation: str, code: str = "ThrottlingException", status: int = 400, message: str = "error") -> "Aws":
        self.stubber.add_client_error(operation, service_error_code=code, service_message=message, http_status_code=status)
        return self

    def operations(self) -> list[str]:
        return [name for name, _ in self.calls]

    def params(self, operation: str) -> dict:
        return next(p for name, p in self.calls if name == operation)

    def done(self) -> None:
        self.stubber.assert_no_pending_responses()


@pytest.fixture
def aws() -> Aws:
    stub = Aws()
    yield stub
    stub.stubber.deactivate()


# ---------------------------------------------------------------------------------------------- images
def jpeg_bytes(size=(1200, 800), color=(120, 90, 60), orientation: int | None = None, quality: int = 90) -> bytes:
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    exif = Image.Exif()
    if orientation:
        exif[0x0112] = orientation
    img.save(buf, format="JPEG", quality=quality, exif=exif.tobytes() if orientation else b"")
    return buf.getvalue()


def png_bytes(size=(1200, 800), color=(30, 160, 90)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def noisy_jpeg(width: int, height: int, quality: int = 95) -> bytes:
    img = Image.frombytes("RGB", (width, height), os.urandom(width * height * 3))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


@pytest.fixture
def jpeg() -> bytes:
    return jpeg_bytes()


@pytest.fixture
def png() -> bytes:
    return png_bytes()
