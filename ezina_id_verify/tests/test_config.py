"""Settings and documents.yaml: what is shipped, what is validated, and how a new document type is added."""
import pytest
from conftest import jpeg_bytes, make_settings
from pydantic import ValidationError

from ezina_id_verify import extract_name
from ezina_id_verify.config import (
    DEFAULT_DOCUMENTS_FILE,
    ConfigError,
    Settings,
    get_settings,
    load_documents,
    set_settings,
)

REQUIRED_TYPES = {
    "passport", "aadhaar", "pan", "voter_id", "driving_licence",  # India (passport: any country)
    "botswana_omang", "kenya_id", "south_africa_id", "nigeria_nin", "ghana_card",  # Africa
    "generic_id",
}

MINIMAL = """
defaults:
  titles: [mr]
  stop_words: [name]
  stop_phrases: []
  skip_labels: ["father's name"]
documents:
  ethiopia_id:
    strategies: [label]
    labels:
      full_name: ["full name"]
"""


def write(tmp_path, text: str):
    p = tmp_path / "documents.yaml"
    p.write_text(text, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------------------------- shipped file
def test_the_shipped_config_is_valid_and_has_every_required_document_type():
    docs = load_documents()
    assert REQUIRED_TYPES <= set(docs.doc_types)
    assert DEFAULT_DOCUMENTS_FILE.exists()


def test_strategy_order_is_configured_per_document():
    docs = load_documents()
    assert docs.documents["passport"].strategies[0] == "mrz"
    assert docs.documents["aadhaar"].strategies == ["layout", "llm"]
    assert docs.documents["pan"].strategies == ["label", "layout", "llm"]


def test_relative_labels_are_skipped_for_every_document():
    skips = " ".join(load_documents().defaults.skip_labels).lower()
    for label in ("father's name", "husband's name", "mother's name", "s/o", "s/d/w of", "son/daughter/wife of"):
        assert label in skips


# ---------------------------------------------------------------------------------------------- malformed files fail clearly
@pytest.mark.parametrize("text,expected", [
    ("documents: [unclosed", "not valid YAML"),
    ("just a string", "must be a mapping"),
    ("defaults: {}\ndocuments: {}", "documents"),
    (MINIMAL.replace("strategies: [label]", "strategy: [label]"), "strategy"),  # a typo in a key
    (MINIMAL.replace("[label]", "[teleport]"), "strategies"),
    (MINIMAL.replace("[label]", "[label, label]"), "twice"),
    (MINIMAL.replace("    labels:\n      full_name: [\"full name\"]\n", ""), "labels section"),
    (MINIMAL.replace("[label]", "[layout]"), "needs a layout"),
    (MINIMAL.replace("[label]", "[layout]\n    layout: sideways"), "layout"),
    (MINIMAL.replace('full_name: ["full name"]', "full_name: []"), "at least one of"),
    (MINIMAL.replace("ethiopia_id", "Ethiopia ID"), "lowercase"),
    (MINIMAL.replace("stop_words: [name]", "stop_words: [no]"), "stop_words"),  # YAML turns an unquoted no into false
    (MINIMAL + "  other:\n    aliases: [ethiopia_id]\n    strategies: [llm]\n", "ethiopia_id"),  # duplicate alias
])
def test_a_malformed_documents_file_fails_with_a_clear_message(tmp_path, text, expected):
    path = write(tmp_path, text)
    with pytest.raises(ConfigError) as e:
        load_documents(path)
    assert expected in str(e.value) and str(path) in str(e.value)


def test_a_missing_file_fails_clearly(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_documents(tmp_path / "nope.yaml")


def test_the_documents_file_can_be_overridden_by_setting(tmp_path):
    set_settings(make_settings(id_verify_documents_config=write(tmp_path, MINIMAL)))
    assert load_documents().doc_types == ["ethiopia_id"]


# ---------------------------------------------------------------------------------------------- new types need only config
async def test_a_new_document_type_needs_only_a_config_entry(tmp_path, aws):
    set_settings(make_settings(id_verify_documents_config=write(tmp_path, MINIMAL)))
    aws.detect_text(["FEDERAL DEMOCRATIC REPUBLIC OF ETHIOPIA", "Full Name: Abebe Bekele", "Father's Name: Kebede"])
    r = await extract_name("ethiopia_id", jpeg_bytes())
    assert r.found and r.full_name == "ABEBE BEKELE" and r.doc_type == "ethiopia_id"


async def test_a_new_label_variant_can_be_added_in_config(tmp_path, aws):
    text = MINIMAL.replace('["full name"]', '["full name", "nom complet"]')
    set_settings(make_settings(id_verify_documents_config=write(tmp_path, text)))
    aws.detect_text(["Nom complet : Awa Diallo"])
    assert (await extract_name("ethiopia_id", jpeg_bytes())).full_name == "AWA DIALLO"


# ---------------------------------------------------------------------------------------------- settings
def test_defaults_match_the_documented_values():
    s = Settings(_env_file=None)
    assert (s.aws_region, s.max_upload_mb, s.name_case, s.llm_fallback_enabled) == ("us-east-1", 10, "upper", False)
    assert (s.face_match_threshold, s.face_possible_match_threshold) == (90, 75)
    assert (s.face_min_sharpness, s.face_min_brightness, s.log_level) == (20, 30, "INFO")
    assert s.id_verify_api_key.get_secret_value() == "" and s.anthropic_api_key.get_secret_value() == ""


def test_settings_come_from_the_environment(monkeypatch):
    for k, v in {"AWS_REGION": "eu-west-1", "MAX_UPLOAD_MB": "4", "NAME_CASE": "title", "LLM_FALLBACK_ENABLED": "true",
                 "FACE_MATCH_THRESHOLD": "95", "FACE_POSSIBLE_MATCH_THRESHOLD": "80", "FACE_MIN_SHARPNESS": "25",
                 "FACE_MIN_BRIGHTNESS": "40", "ID_VERIFY_API_KEY": "k", "LOG_LEVEL": "debug", "CLAUDE_MODEL": "m",
                 "ANTHROPIC_API_KEY": "a"}.items():
        monkeypatch.setenv(k, v)
    set_settings(None)
    s = get_settings()
    assert (s.aws_region, s.max_upload_mb, s.name_case, s.llm_fallback_enabled) == ("eu-west-1", 4, "title", True)
    assert (s.face_match_threshold, s.face_possible_match_threshold, s.log_level) == (95, 80, "DEBUG")
    assert s.claude_model == "m" and s.id_verify_api_key.get_secret_value() == "k"


def test_secrets_are_not_shown_in_repr():
    s = Settings(_env_file=None, anthropic_api_key="sk-secret", id_verify_api_key="api-secret")
    assert "sk-secret" not in repr(s) and "api-secret" not in repr(s)


@pytest.mark.parametrize("env", [
    {"NAME_CASE": "shouting"}, {"FACE_MATCH_THRESHOLD": "150"}, {"LOG_LEVEL": "loud"}, {"MAX_UPLOAD_MB": "0"},
    {"FACE_MATCH_THRESHOLD": "50"},  # below the default possible-match threshold (75)
])
def test_invalid_settings_fail_clearly(monkeypatch, env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    set_settings(None)
    with pytest.raises(ConfigError, match="invalid settings"):
        get_settings()


def test_possible_match_threshold_cannot_exceed_the_match_threshold():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, face_match_threshold=80, face_possible_match_threshold=85)
