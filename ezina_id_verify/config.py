"""Settings (environment / .env) and loading + validation of config/documents.yaml.

A malformed documents.yaml fails with a ConfigError that names the file and the problem; the optional HTTP wrapper
loads it at startup, library callers get the error on first use (or call `load_documents()` themselves at startup).
"""
from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_LOGGER = "ezina_id_verify"
DEFAULT_DOCUMENTS_FILE = Path(__file__).resolve().parent / "config" / "documents.yaml"

Strategy = Literal["mrz", "label", "layout", "llm"]
LayoutKind = Literal["aadhaar_above_dob", "pan_header", "first_name_line"]


class ConfigError(ValueError):
    """The settings or documents.yaml are invalid. The message says what to fix."""


# ---------------------------------------------------------------------------------------------- settings
class Settings(BaseSettings):
    """Environment variables (or a .env file in the working directory). Unknown variables are ignored."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False)

    aws_region: str = "us-east-1"  # credentials come from the standard AWS credential chain
    aws_max_retries: int = Field(3, ge=0, le=10)  # retries on throttling / 5xx / network errors
    aws_retry_base_delay: float = Field(0.5, ge=0)  # exponential backoff base, seconds
    max_upload_mb: float = Field(10.0, gt=0)
    name_case: Literal["upper", "title", "original"] = "upper"
    llm_fallback_enabled: bool = False
    anthropic_api_key: SecretStr = SecretStr("")
    claude_model: str = ""
    face_match_threshold: float = Field(90.0, ge=0, le=100)
    face_possible_match_threshold: float = Field(75.0, ge=0, le=100)
    face_min_sharpness: float = Field(20.0, ge=0, le=100)
    face_min_brightness: float = Field(30.0, ge=0, le=100)
    face_id_min_width: float = Field(0.06, ge=0, le=1)  # ID face narrower than this (fraction of image width): "small_face_id"
    id_verify_api_key: SecretStr = SecretStr("")  # HTTP wrapper only
    id_verify_documents_config: Path | None = None  # override the bundled documents.yaml
    log_level: str = "INFO"

    @field_validator("log_level")
    @classmethod
    def _log_level(cls, v: str) -> str:
        v = v.strip().upper()
        if not isinstance(logging.getLevelName(v), int):
            raise ValueError(f"unknown log level {v!r}")
        return v

    @model_validator(mode="after")
    def _thresholds_are_ordered(self) -> "Settings":
        if self.face_possible_match_threshold > self.face_match_threshold:
            raise ValueError("FACE_POSSIBLE_MATCH_THRESHOLD must not be above FACE_MATCH_THRESHOLD")
        return self


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        try:
            _settings = Settings()
        except ValidationError as e:
            raise ConfigError(f"invalid settings: {_describe(e)}") from e
        logging.getLogger(PACKAGE_LOGGER).setLevel(_settings.log_level)
    return _settings


def set_settings(settings: Settings | None) -> None:
    """Use these settings from now on (None: reload from the environment on next use). Mainly for tests."""
    global _settings
    _settings = settings


# ---------------------------------------------------------------------------------------------- documents.yaml
class LabelSpec(BaseModel):
    """Field labels printed on the document, as they are written (matching is case-insensitive, OCR-tolerant)."""

    model_config = ConfigDict(extra="forbid")

    full_name: list[str] = Field(default_factory=list)  # a single full-name label ("Name", "Full Names")
    surname: list[str] = Field(default_factory=list)  # separate surname label variants
    # One or more groups of label variants; each group is one field, values are joined in order
    # ("First Name" + "Middle Name"). Written as a list of lists.
    given_names: list[list[str]] = Field(default_factory=list)
    skip: list[str] = Field(default_factory=list)  # labels whose value is never the cardholder (this document only)

    @model_validator(mode="after")
    def _something_to_look_for(self) -> "LabelSpec":
        if not (self.full_name or self.surname or self.given_names):
            raise ValueError("labels needs at least one of full_name, surname or given_names")
        if any(not g for g in self.given_names):
            raise ValueError("given_names groups must not be empty")
        return self


class DocumentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    country: str | None = None
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    strategies: list[Strategy] = Field(min_length=1)  # tried in this order
    labels: LabelSpec | None = None
    layout: LayoutKind | None = None
    stop_words: list[str] = Field(default_factory=list)  # extra words that are never part of a name here
    stop_phrases: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _strategies_have_what_they_need(self) -> "DocumentSpec":
        if len(set(self.strategies)) != len(self.strategies):
            raise ValueError("strategies lists a strategy twice")
        if "label" in self.strategies and self.labels is None:
            raise ValueError("the 'label' strategy needs a labels section")
        if "layout" in self.strategies and self.layout is None:
            raise ValueError("the 'layout' strategy needs a layout (aadhaar_above_dob, pan_header or first_name_line)")
        return self


class Defaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titles: list[str] = Field(default_factory=list)  # removed from the start of a name
    stop_words: list[str] = Field(default_factory=list)  # single words that make a line "not a name" (layout strategies)
    stop_phrases: list[str] = Field(default_factory=list)  # header phrases that are never a name
    skip_labels: list[str] = Field(default_factory=list)  # relative-name labels, never returned (every document)


_KEY = re.compile(r"^[a-z0-9_]+$")


def normalise_doc_type(doc_type: str) -> str:
    return str(doc_type or "").strip().lower().replace("-", "_").replace(" ", "_")


class DocumentsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    defaults: Defaults
    documents: dict[str, DocumentSpec] = Field(min_length=1)

    @field_validator("documents")
    @classmethod
    def _keys_are_clean(cls, v: dict[str, DocumentSpec]) -> dict[str, DocumentSpec]:
        seen: dict[str, str] = {}
        for key, spec in v.items():
            if not _KEY.match(key):
                raise ValueError(f"document type {key!r} must be lowercase letters, digits and underscores")
            for name in [key, *spec.aliases]:
                n = normalise_doc_type(name)
                if n in seen and seen[n] != key:
                    raise ValueError(f"{name!r} is used by both {seen[n]!r} and {key!r}")
                seen[n] = key
        return v

    def lookup(self, doc_type: str) -> tuple[str, DocumentSpec] | None:
        """(canonical key, spec) for a doc_type or one of its aliases, else None."""
        wanted = normalise_doc_type(doc_type)
        for key, spec in self.documents.items():
            if wanted == key or wanted in {normalise_doc_type(a) for a in spec.aliases}:
                return key, spec
        return None

    @property
    def doc_types(self) -> list[str]:
        return list(self.documents)


def _describe(e: ValidationError) -> str:
    parts = []
    for err in e.errors():
        where = ".".join(str(p) for p in err["loc"]) or "(root)"
        parts.append(f"{where}: {err['msg']}")
    return "; ".join(parts)


@lru_cache(maxsize=8)
def _load(path: str) -> DocumentsConfig:
    p = Path(path)
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise ConfigError(f"documents config not found: {p}") from e
    except yaml.YAMLError as e:
        raise ConfigError(f"documents config {p} is not valid YAML: {e}") from e
    if not isinstance(raw, dict):
        raise ConfigError(f"documents config {p} must be a mapping with 'defaults' and 'documents'")
    try:
        return DocumentsConfig.model_validate(raw)
    except ValidationError as e:
        raise ConfigError(f"documents config {p} is invalid: {_describe(e)}") from e


def load_documents(path: str | Path | None = None) -> DocumentsConfig:
    """Load and validate documents.yaml (cached). Raises ConfigError with a clear message when it is malformed."""
    if path is None:
        path = get_settings().id_verify_documents_config or DEFAULT_DOCUMENTS_FILE
    return _load(str(Path(path)))


def reset_documents_cache() -> None:
    _load.cache_clear()
