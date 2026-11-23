"""Application settings, loaded from environment / .env via pydantic-settings."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # .../ezina-connect


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BASE_DIR.parent / ".env", BASE_DIR / ".env"),
        extra="ignore",
        case_sensitive=False,
    )

    # --- Anthropic ---
    anthropic_api_key: SecretStr = SecretStr("")
    claude_model: str = "claude-sonnet-5-5"
    claude_max_tokens: int = 1024
    claude_max_retries: int = 4  # SDK retries 429/5xx/overloaded with exponential backoff
    claude_timeout_seconds: float = 30.0

    # --- WhatsApp / Meta ---
    whatsapp_access_token: SecretStr = SecretStr("")
    whatsapp_phone_number_id: str = ""
    whatsapp_business_account_id: str = ""
    whatsapp_verify_token: SecretStr = SecretStr("")
    meta_app_secret: SecretStr = SecretStr("")
    whatsapp_graph_api_version: str = "v21.0"
    whatsapp_max_retries: int = 4
    whatsapp_retry_base_delay: float = 1.0
    # Approved templates used outside the 24h window (optional)
    whatsapp_template_language: str = "en"
    whatsapp_template_verification: str = ""  # one body param: status text

    # --- Database ---
    database_url: str = "sqlite+aiosqlite:///./ezina_dev.db"

    # --- Admin ---
    admin_api_key: SecretStr = SecretStr("")
    ops_webhook_url: str = ""  # optional: POSTed on human handoff

    # --- Media ---
    media_storage_backend: str = "local"  # local | s3
    media_local_dir: str = "./media_store"
    s3_bucket: str = ""
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: SecretStr = SecretStr("")
    # Identity images (ID photo, selfie) live in a separate private, encrypted bucket; never public URLs.
    s3_identity_bucket: str = ""
    identity_local_dir: str = ""  # local backend only; default: "<MEDIA_LOCAL_DIR>_identity"
    max_media_bytes: int = 8 * 1024 * 1024
    allowed_image_mime: tuple[str, ...] = ("image/jpeg", "image/png", "image/webp")

    # --- Identity verification (ID document + selfie) ---
    identity_max_attempts: int = 3  # failed uploads per image before NEEDS_HELP
    identity_min_image_px: int = 600  # minimum length of the shorter side
    identity_max_bytes: int = 10 * 1024 * 1024
    identity_allowed_mime: tuple[str, ...] = ("image/jpeg", "image/png", "image/webp")
    identity_document_mime: tuple[str, ...] = ("image/jpeg", "image/png", "application/pdf")  # ID sent as a document
    selfie_challenge_ttl_minutes: int = 10

    # --- ID document name check (external document-extraction API; advisory only) ---
    doc_extract_enabled: bool = False
    doc_extract_api_url: str = ""
    doc_extract_api_key: SecretStr = SecretStr("")
    doc_extract_api_key_header: str = "Authorization"  # "Authorization" is sent as "Bearer <key>"; any other header gets the bare key
    doc_extract_timeout_seconds: float = 30.0
    doc_extract_max_retries: int = 2  # retries on timeout / connection error / 5xx (never 4xx)
    doc_extract_retry_base_delay: float = 1.0  # exponential backoff base, seconds
    doc_extract_hold_seconds: float = 5.0  # send "Checking your ID..." when the check takes longer than this
    name_match_threshold: float = 90  # score >= this: MATCHED
    name_partial_threshold: float = 75  # score >= this: PARTIAL, below: MISMATCH
    name_check_max_attempts: int = 3  # failed name comparisons (name changes + new IDs) before NEEDS_HELP

    # --- Selfie face check (external face-verification API; advisory only) ---
    face_verify_enabled: bool = False
    face_verify_api_url: str = ""
    face_verify_api_key: SecretStr = SecretStr("")
    face_verify_api_key_header: str = "Authorization"  # "Authorization" is sent as "Bearer <key>"; any other header gets the bare key
    face_verify_timeout_seconds: float = 60.0  # the API can take ~15 seconds
    face_verify_max_retries: int = 2  # retries on timeout / connection error / 5xx (never 4xx)
    face_verify_retry_base_delay: float = 1.0  # exponential backoff base, seconds
    face_verify_max_attempts: int = 3  # failed face checks (new selfies + new IDs) before NEEDS_HELP
    face_verify_sharpen_retry: bool = True  # on a "too blurry" quality rejection, retry once with a mildly sharpened copy

    # --- Workflow tuning ---
    min_farm_photos: int = 1
    low_confidence_threshold: float = 0.6
    history_limit: int = 10
    rate_limit_per_minute: int = 20
    resume_greeting_after_hours: int = 6
    max_processing_attempts: int = 3
    supported_languages: dict[str, str] = {
        "en": "English",
        "tn": "Setswana",
        "hi": "Hindi",
        "mr": "Marathi",
        "ta": "Tamil",
        "te": "Telugu",
        "sw": "Kiswahili",
    }

    # --- Logging / env ---
    log_level: str = "INFO"
    app_env: str = "development"  # development | production

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
