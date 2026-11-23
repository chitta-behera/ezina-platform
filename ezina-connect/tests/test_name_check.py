"""ID name check: the ezina_id_verify integration, the config, name matching and the farmer-facing flow.

ezina_id_verify.extract_name is mocked (AWS is never called). The name read from an ID is sensitive: these tests also
prove it never reaches a log, a farmer message or a Claude prompt.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid

import pytest
from sqlalchemy import select
from ezina_id_verify import NameResult, RekognitionServiceError, UnsupportedDocType, UnsupportedFile

from app.config import Settings
from app.enums import Intent, NameCheckStatus
from app.models import Conversation, IdentityDocument
from app.services import doc_extract_service, name_match
from app.services.claude_service import build_user_message
from app.services.doc_extract_service import DocExtractService
from app.workflows import identity_flow
from app.workflows import messages as M
from tests.conftest import ADMIN_KEY, make_ai, make_image

ID_NAME = "Mokoena Thabo Zuma"  # a distinctive name "printed on the ID": must never leak


# ------------------------------------------------------------------ the mocked ezina_id_verify.extract_name
def found(doc_type: str, name: str, **over) -> NameResult:
    """A NameResult with only full_name set (given_names / surname stay None, as for most documents)."""
    base = dict(doc_type=doc_type, found=True, full_name=name, method="label", confidence=0.85, warnings=[])
    return NameResult(**{**base, **over})


def not_found(doc_type: str) -> NameResult:
    return NameResult(doc_type=doc_type, found=False, confidence=0.0, warnings=["name_not_found"])


class ExtractMock:
    """Stands in for ezina_id_verify.extract_name: records the calls, answers from a script, never touches AWS."""

    def __init__(self):
        self.requests: list[tuple[str, bytes]] = []  # (doc_type, id_image) per call
        self.script: list = []  # NameResult | Exception | callable(doc_type) -> NameResult, popped first
        self.default: NameResult | None = None  # None: the name below, with the doc_type that was asked for
        self.delay = 0.0
        self._name = ID_NAME

    async def __call__(self, doc_type: str, image: bytes) -> NameResult:
        self.requests.append((doc_type, image))
        if self.delay:
            await asyncio.sleep(self.delay)
        item = self.script.pop(0) if self.script else (self.default or found(doc_type, self._name))
        if isinstance(item, Exception):
            raise item
        return item(doc_type) if callable(item) else item

    def name(self, value: str) -> None:
        self._name, self.default = value, None


@pytest.fixture
def make_service(monkeypatch):
    def factory(**overrides) -> tuple[DocExtractService, ExtractMock]:
        mock = ExtractMock()
        monkeypatch.setattr(doc_extract_service, "extract_name", mock)
        return DocExtractService(Settings(**{"_env_file": None, "doc_extract_enabled": True, **overrides})), mock

    return factory


@pytest.fixture
def api(env, monkeypatch):
    """The running app with the name check switched on and extract_name mocked."""
    mock = ExtractMock()
    monkeypatch.setattr(doc_extract_service, "extract_name", mock)
    s = env.c.settings
    s.doc_extract_enabled = True
    env.c.doc_extract = DocExtractService(s)
    return mock


async def to_passport(env, *, send_photo: bool = True):
    """Registration up to the ID step, with a Botswana passport chosen (the farmer's name is "John")."""
    await env.run_registration_until("location")
    await env.button("idtype_PASSPORT", "Passport")
    if send_photo:
        await env.identity_image()


async def draft(env) -> dict:
    return (await env.conv()).draft


async def docs(env, *where):
    return await env.all(IdentityDocument, *where)


async def front(env) -> IdentityDocument:
    rows = [d for d in await docs(env) if d.kind == "ID_FRONT"]
    return rows[-1]


# ------------------------------------------------------------------ 1. the service calls ezina_id_verify
@pytest.mark.parametrize("code,doc_type", [
    ("PASSPORT", "passport"), ("AADHAAR_MASKED", "aadhaar"), ("PAN", "pan"), ("VOTER_ID", "voter_id"),
    ("DRIVING_LICENCE", "driving_licence"), ("OMANG", "botswana_omang"),
])
async def test_each_id_type_passes_its_own_doc_type_and_only_the_image_bytes(make_service, code, doc_type):
    svc, mock = make_service()
    out = await svc.extract_name(id_document_type=code, data=b"IMGBYTES")
    assert mock.requests == [(doc_type, b"IMGBYTES")]  # raw bytes only: no content type
    assert out.status == NameCheckStatus.PENDING and out.name == ID_NAME
    assert (out.method, out.confidence, out.unsupported_file) == ("label", 0.85, False)


@pytest.mark.parametrize("code", ["KCC", None, "NOPE"])
async def test_an_id_type_without_a_verify_doc_type_is_skipped_without_calling_the_package(make_service, code):
    svc, mock = make_service()
    out = await svc.extract_name(id_document_type=code, data=b"IMG")
    assert out.status == NameCheckStatus.SKIPPED and out.name is None and mock.requests == []
    assert svc.verify_doc_type(code) is None


async def test_switched_off_is_skipped_without_calling_the_package(make_service):
    svc, mock = make_service(doc_extract_enabled=False)
    assert not svc.available
    assert (await svc.extract_name(id_document_type="PASSPORT", data=b"IMG")).status == NameCheckStatus.SKIPPED
    assert mock.requests == []


async def test_a_result_with_only_full_name_is_enough(make_service):
    svc, mock = make_service()
    mock.default = found("pan", "  rajesh   KUMAR ", given_names=None, surname=None)
    out = await svc.extract_name(id_document_type="PAN", data=b"IMG")
    assert out.status == NameCheckStatus.PENDING and out.name == "rajesh KUMAR"  # whitespace normalised, nothing else


async def test_found_false_is_not_found_and_an_empty_name_is_too(make_service):
    svc, mock = make_service()
    mock.default = not_found("passport")
    out = await svc.extract_name(id_document_type="PASSPORT", data=b"IMG")
    assert out.status == NameCheckStatus.NOT_FOUND and out.name is None and not out.unsupported_file
    mock.default = found("passport", "   ")
    assert (await svc.extract_name(id_document_type="PASSPORT", data=b"IMG")).status == NameCheckStatus.NOT_FOUND


@pytest.mark.parametrize("failure,status,unsupported,reason", [
    (UnsupportedDocType("nope"), NameCheckStatus.SKIPPED, False, "unsupported_doc_type"),
    (UnsupportedFile("not a JPEG/PNG"), NameCheckStatus.NOT_FOUND, True, "unsupported_file"),
    (RekognitionServiceError("AWS failed", "ThrottlingException"), NameCheckStatus.ERROR, False, "ThrottlingException"),
    (RuntimeError("anything else"), NameCheckStatus.ERROR, False, "RuntimeError"),
])
async def test_package_exceptions_become_statuses_and_never_reach_the_caller(make_service, failure, status, unsupported, reason):
    svc, mock = make_service()
    mock.script = [failure, failure, failure]
    out = await svc.extract_name(id_document_type="PASSPORT", data=b"IMG")
    assert (out.status, out.unsupported_file, out.reason, out.name) == (status, unsupported, reason, None)
    assert len(mock.requests) == 1  # ezina_id_verify already retries AWS errors: nothing is retried here


async def test_a_doc_type_that_differs_from_the_one_passed_is_logged_without_personal_data(make_service, caplog):
    svc, mock = make_service()
    mock.default = found("generic_id", ID_NAME)
    with caplog.at_level(logging.WARNING, logger="ezina"):
        out = await svc.extract_name(id_document_type="PASSPORT", data=b"IMG")
    assert out.status == NameCheckStatus.PENDING  # still usable
    assert "differs" in caplog.text and ID_NAME not in app_log_text(caplog)


async def test_the_service_logs_status_method_confidence_and_timing_but_never_the_name(make_service, caplog):
    svc, mock = make_service()
    mock.default = found("passport", ID_NAME, given_names="Thabo Zuma", surname="Mokoena", warnings=["x"])
    with caplog.at_level(logging.DEBUG, logger="ezina"):
        await svc.extract_name(id_document_type="PASSPORT", data=b"IMG")
    text = app_log_text(caplog)
    assert "name check call" in text and "PENDING" in text and "label" in text and "0.85" in text
    for secret in (ID_NAME, "Thabo", "Mokoena", "Zuma"):
        assert secret not in text


# ------------------------------------------------------------------ 2. per-document configuration
def test_configured_id_types_and_those_without_configuration():
    expected = {"PASSPORT": "passport", "AADHAAR_MASKED": "aadhaar", "PAN": "pan", "VOTER_ID": "voter_id",
                "DRIVING_LICENCE": "driving_licence", "OMANG": "botswana_omang"}
    for code, doc_type in expected.items():
        assert identity_flow.extraction_for(code).verify_doc_type == doc_type
    for code in ("KCC", None, "NOPE"):
        assert identity_flow.extraction_for(code) is None


def test_every_shipped_verify_doc_type_is_a_document_type_ezina_id_verify_knows():
    from ezina_id_verify.config import load_documents

    known = set(load_documents().doc_types)
    for code in ("PASSPORT", "AADHAAR_MASKED", "PAN", "VOTER_ID", "DRIVING_LICENCE", "OMANG"):
        assert identity_flow.extraction_for(code).verify_doc_type in known


GOOD = """
countries:
  BW:
    types:
      - {code: PASSPORT, names: {en: "Passport"}}
      - {code: OMANG, names: {en: "Omang"}}
extraction:
  PASSPORT: {verify_doc_type: passport}
"""


@pytest.fixture
def config_file(tmp_path, monkeypatch):
    path = tmp_path / "id_documents.yaml"
    monkeypatch.setattr(identity_flow, "CONFIG_PATH", path)
    identity_flow._load.cache_clear()
    yield path
    monkeypatch.undo()
    identity_flow._load.cache_clear()


def test_new_document_type_needs_only_a_config_change(config_file):
    config_file.write_text(GOOD.replace("extraction:", "extraction:\n  OMANG: {verify_doc_type: kenya_id}"))
    identity_flow.validate_config()
    assert identity_flow.extraction_for("OMANG").verify_doc_type == "kenya_id"


@pytest.mark.parametrize("bad,message", [
    ("just: a mapping", "'countries'"),
    (GOOD.replace("verify_doc_type: passport", "doc_type: passport, name_fields: [name]"), "extraction.PASSPORT: 'verify_doc_type'"),
    (GOOD.replace("{verify_doc_type: passport}", "{verify_doc_type: ''}"), "extraction.PASSPORT: 'verify_doc_type'"),
    (GOOD.replace("{verify_doc_type: passport}", "{verify_doc_type: [passport]}"), "extraction.PASSPORT: 'verify_doc_type'"),
    (GOOD.replace("{verify_doc_type: passport}", "passport"), "extraction.PASSPORT: 'verify_doc_type'"),
    (GOOD.replace("PASSPORT: {verify", "GHOST: {verify"), "'GHOST' is not an ID type"),
    (GOOD.replace("extraction:\n  PASSPORT: {verify_doc_type: passport}", "extraction: [1, 2]"), "'extraction' must be a mapping"),
    (GOOD.replace('{en: "Passport"}', "{}"), "needs an 'en' entry"),
    ("countries: [unclosed", "not valid YAML"),
])
def test_malformed_config_fails_clearly_at_startup(config_file, bad, message):
    config_file.write_text(bad)
    with pytest.raises(identity_flow.ConfigError) as e:
        identity_flow.validate_config()
    assert message in str(e.value) and str(e.value).startswith("id_documents.yaml:")


def test_shipped_config_is_valid():
    identity_flow._load.cache_clear()
    identity_flow.validate_config()


_STD_RECORD_FIELDS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}  # timing floats are noise


def app_log_text(caplog) -> str:
    """Everything the app itself logged (message and structured fields); SQL driver debug output is not ours."""
    return " ".join(
        f"{r.getMessage()} {sorted((k, v) for k, v in r.__dict__.items() if k not in _STD_RECORD_FIELDS)}"
        for r in caplog.records if r.name.startswith("ezina")
    )


# ------------------------------------------------------------------ 3. name matching
@pytest.mark.parametrize("failure", [
    RekognitionServiceError("AWS failed", "ThrottlingException"), RekognitionServiceError("denied", "AccessDeniedException"),
    RuntimeError("anything else"),
])
async def test_failure_does_not_block_the_farmer(env, api, failure):
    api.script = [failure] * 3
    await to_passport(env)
    assert len(api.requests) == 1  # nothing is retried here: ezina_id_verify already retries AWS errors
    d = await front(env)
    assert d.name_check_status == "ERROR" and d.extracted_name is None and d.name_checked_at is not None
    assert d.name_extract_method is None and d.name_extract_confidence is None
    assert await env.stage() == "COLLECT_SELFIE"
    assert "doesn't match" not in " ".join(env.graph.texts()) and "Got it" in env.graph.texts()[-1]
    assert (await draft(env))["id_front_doc"] == str(d.id)


HOLD = "Thank you! Checking your ID, this takes a few seconds…"


async def test_the_farmer_is_told_the_id_is_being_checked_before_the_result(env, api):
    api.name("John")
    await to_passport(env)
    texts = env.graph.texts()
    assert texts.count(HOLD) == 1 and texts.index(HOLD) < len(texts) - 1  # before the real reply
    assert (await front(env)).name_check_status == "MATCHED"


async def test_no_checking_message_when_no_check_runs(env, api, config_file):
    config_file.write_text(GOOD)  # OMANG has no verify_doc_type: nothing is checked
    identity_flow.validate_config()
    await env.run_registration_until("id_front")
    assert api.requests == [] and HOLD not in env.graph.texts()


async def test_no_checking_message_when_the_check_is_off(env, api):
    env.c.settings.doc_extract_enabled = False
    await to_passport(env)
    assert api.requests == [] and HOLD not in env.graph.texts()


# ------------------------------------------------------------------ 6. flow: the farmer's choices
async def test_change_my_name_updates_the_name_and_recompares_without_calling_the_api_again(env, api):
    await to_passport(env)
    await env.button("name_change", "Change my name")
    assert env.graph.texts()[-1] == "Please type your full name exactly as it is written on your ID."
    await env.text(ID_NAME)  # a name typed as written on the ID: no Claude call needed
    assert len(api.requests) == 1  # no new API call
    d = await front(env)
    assert d.name_check_status == "MATCHED" and d.name_check_attempts == 1
    dr = await draft(env)
    assert dr["full_name"] == ID_NAME and dr["id_front_doc"] == str(d.id) and not dr["name_choice_pending"]
    assert await env.stage() == "COLLECT_SELFIE"


async def test_a_new_name_that_still_does_not_match_offers_the_buttons_again(env, api):
    await to_passport(env)
    await env.button("name_change")
    await env.text("Peter Dlamini")
    assert env.graph.last_buttons() == ["name_change", "id_reupload"]
    assert "(Peter Dlamini)" in env.graph.texts()[-1]
    assert (await front(env)).name_check_attempts == 2 and len(api.requests) == 1


async def test_an_invalid_new_name_is_asked_for_again(env, api):
    await to_passport(env)
    await env.button("name_change")
    await env.text("12345 <>")
    assert "doesn't look like a name" in env.graph.texts()[-1]
    assert (await draft(env))["name_awaiting"] is True
    await env.text(ID_NAME)
    assert (await front(env)).name_check_status == "MATCHED"


async def test_upload_another_id_supersedes_the_old_one_and_checks_the_new_one(env, api):
    await to_passport(env)
    first = await front(env)
    await env.button("id_reupload", "Upload another ID")
    assert env.graph.last()["interactive"]["action"].get("sections")  # back to the ID type list
    assert await docs(env, IdentityDocument.id == first.id) == []  # the old ID is deleted, not kept
    api.name("John")  # the next ID carries the farmer's name
    await env.button("idtype_PASSPORT", "Passport")
    await env.identity_image()
    assert len(api.requests) == 2  # the new document is sent to the API
    second = await front(env)
    assert second.id != first.id and second.name_check_status == "MATCHED"
    assert await env.stage() == "COLLECT_SELFIE"
    assert (await draft(env))["name_check_attempts"] == 1  # the earlier mismatch still counts


async def test_free_text_a_new_name_is_treated_as_change_my_name(env, api):
    await to_passport(env)
    env.claude.push(make_ai(Intent.CORRECT_INFORMATION, full_name=ID_NAME))
    await env.text(f"my name is {ID_NAME}")
    assert len(api.requests) == 1 and (await front(env)).name_check_status == "MATCHED"
    assert (await draft(env))["full_name"] == ID_NAME


async def test_free_text_asking_for_a_different_id_is_treated_as_upload_another(env, api):
    await to_passport(env)
    first = await front(env)
    env.claude.push(make_ai(Intent.SUBMIT_IDENTITY_DOCUMENTS))
    await env.text("I will send my other document")
    assert await docs(env, IdentityDocument.id == first.id) == []
    assert not (await draft(env))["name_choice_pending"]


async def test_free_text_deterministic_phrases_need_no_claude(env, api):
    await to_passport(env)
    calls = len(env.claude.contexts)
    await env.text("change my name")
    assert (await draft(env))["name_awaiting"] is True
    await env.text("Peter Dlamini")
    await env.text("Upload another ID")
    assert not (await draft(env))["name_choice_pending"] and len(env.claude.contexts) == calls  # no model call at all


async def test_other_free_text_shows_the_two_buttons_again(env, api):
    await to_passport(env)
    env.claude.push(make_ai(Intent.GREETING))
    await env.text("hello?")
    assert env.graph.last_buttons() == ["name_change", "id_reupload"]
    assert (await draft(env))["name_choice_pending"]


async def test_stop_is_still_honoured_while_the_choice_is_open(env, api):
    await to_passport(env)
    env.claude.push(make_ai(Intent.CANCEL_REGISTRATION))
    await env.text("cancel registration")
    assert "stop your registration" in env.graph.texts()[-1].lower()


async def test_photo_or_other_buttons_while_the_choice_is_open_show_the_choice_again(env, api):
    await to_passport(env)
    await env.identity_image()
    assert env.graph.last_buttons() == ["name_change", "id_reupload"] and len(api.requests) == 1
    await env.button("id_later", "Send later")
    assert env.graph.last_buttons() == ["name_change", "id_reupload"]
    assert not (await draft(env))["id_deferred"]


async def test_stale_choice_buttons_are_ignored_when_nothing_is_pending(env, api):
    api.name("John")
    await to_passport(env)
    await env.button("name_change")
    assert await env.stage() == "COLLECT_SELFIE" and not (await draft(env))["name_awaiting"]


# ------------------------------------------------------------------ 7. attempt limit
async def test_after_the_maximum_attempts_the_team_reviews_and_the_flow_continues(env, api):
    await to_passport(env)  # attempt 1
    await env.button("name_change")
    await env.text("Peter Dlamini")  # attempt 2
    await env.button("id_reupload")
    await env.button("idtype_PASSPORT")
    await env.identity_image()  # attempt 3: stop asking
    texts = env.graph.texts()
    assert "Ezina team will review your ID" in texts[-2] or "Ezina team will review your ID" in texts[-1]
    dr = await draft(env)
    assert dr["id_needs_help"] and not dr["name_choice_pending"] and dr["id_front_doc"] is None
    assert await env.stage() == "COLLECT_SELFIE"
    row = await front(env)
    assert row.name_check_status == "MISMATCH" and row.name_check_attempts == 3 and row.extracted_name == ID_NAME
    await env.identity_image()  # selfie
    await env.button("farmphoto_skip")
    await env.button("cropphoto_skip")
    await env.button("review_confirm", "Confirm")
    f = await env.farmer()
    assert f.id_document_status == "NEEDS_HELP" and f.verification_status != "VERIFIED"


async def test_attempt_limit_is_configurable(env, api):
    env.c.settings.name_check_max_attempts = 1
    await to_passport(env)
    assert (await draft(env))["id_needs_help"] and await env.stage() == "COLLECT_SELFIE"


# ------------------------------------------------------------------ 8. privacy and Claude
async def test_extracted_name_never_reaches_logs_claude_or_farmer_messages(env, api, caplog):
    with caplog.at_level(logging.DEBUG, logger="ezina"):
        await to_passport(env)
        env.claude.push(make_ai(Intent.GREETING))
        await env.text("hello?")
        await env.button("name_change")
        await env.text("Peter Dlamini")
    assert env.claude.contexts, "Claude must have been called at least once"
    for ctx in env.claude.contexts:
        prompt = build_user_message(ctx)
        for secret in (ID_NAME, "Thabo", "UHN8691735", "Niranjan Behera"):
            assert secret not in prompt
    for secret in (ID_NAME, "UHN8691735", "Niranjan Behera"):
        assert secret not in app_log_text(caplog)
        assert secret not in " ".join(env.graph.texts())
        assert secret not in json.dumps((await draft(env)))


async def test_non_english_mismatch_wording_comes_from_claude_and_is_guarded(env, api):
    await env.run_registration_until("location")
    async with env.c.db.sessionmaker() as s, s.begin():
        conv = await s.get(Conversation, (await env.conv()).id)
        conv.draft = {**conv.draft, "preferred_language": "tn"}
    await env.button("idtype_PASSPORT")
    env.claude.push(make_ai(text="Leina le le mo ID ga le tshwane le le o neng a le file. Tlhopha tsela."))
    await env.identity_image()
    assert env.graph.texts()[-1].startswith("Leina le le mo ID") and env.graph.last_buttons() == ["name_change", "id_reupload"]
    ctx = env.claude.contexts[-1]
    assert ctx.mode == "compose" and "name_given" in ctx.saved_summary
    assert ID_NAME not in build_user_message(ctx)


async def test_unsafe_non_english_wording_falls_back_to_the_template(env, api):
    await env.run_registration_until("location")
    async with env.c.db.sessionmaker() as s, s.begin():
        conv = await s.get(Conversation, (await env.conv()).id)
        conv.draft = {**conv.draft, "preferred_language": "tn"}
    await env.button("idtype_PASSPORT")
    env.claude.push(make_ai(text="Your ID is fake. Send your ID number 1234567890123 now."))
    await env.identity_image()
    assert env.graph.texts()[-1].startswith("The name on your ID doesn't match")


async def test_admin_detail_returns_the_extracted_name_and_the_result(env, api):
    await to_passport(env)
    f = await env.farmer()
    r = await env.client.get(f"/api/admin/farmers/{f.id}", headers={"X-API-Key": ADMIN_KEY})
    (ident,) = [d for d in r.json()["identity_documents"] if d["kind"] == "ID_FRONT"]
    assert ident["extracted_name"] == ID_NAME and ident["name_check_status"] == "MISMATCH"
    assert ident["name_match_score"] is not None and ident["name_check_attempts"] == 1
    listing = await env.client.get("/api/admin/farmers", headers={"X-API-Key": ADMIN_KEY})
    assert ID_NAME not in listing.text


async def test_the_check_never_verifies_a_farmer(env, api):
    api.name("John")
    await to_passport(env)
    await env.identity_image()
    await env.button("farmphoto_skip")
    await env.button("cropphoto_skip")
    await env.button("review_confirm", "Confirm")
    f = await env.farmer()
    assert f.verification_status == "PENDING" and f.verification_status != "VERIFIED"


# ------------------------------------------------------------------ 8b. the Rekognition integration in the flow
@pytest.mark.parametrize("button,label,doc_type", [
    ("idtype_PASSPORT", "Passport", "passport"), ("idtype_OMANG", "Omang", "botswana_omang"),
    ("idtype_DRIVING_LICENCE", "Driving licence", "driving_licence"),
])
async def test_the_selected_id_type_decides_the_doc_type_passed_to_the_package(env, api, button, label, doc_type):
    api.name("John")
    await env.run_registration_until("location")
    await env.button(button, label)
    await env.identity_image()
    (row,) = [d for d in await docs(env) if d.kind == "ID_FRONT"]
    stored = await env.c.identity.storage.get(row.storage_key)
    assert api.requests == [(doc_type, stored)]  # the stored ID front's bytes, nothing else
    assert row.name_check_status == "MATCHED"


async def test_unsupported_file_asks_for_a_clear_jpeg_png_photo_and_counts_as_an_attempt(env, api):
    api.script = [UnsupportedFile("not a JPEG/PNG")]
    await to_passport(env)
    assert env.graph.texts()[-1].startswith(M.ID_SEND_PHOTO)
    assert [d for d in await docs(env) if d.kind == "ID_FRONT"] == []  # the unusable photo and its row are removed
    assert (await draft(env))["id_attempts"] == 1 and await env.stage() == "COLLECT_ID_DOCUMENT"
    api.name("John")
    await env.identity_image()  # a good photo now
    assert await env.stage() == "COLLECT_SELFIE" and (await front(env)).name_check_status == "MATCHED"


async def test_unsupported_doc_type_skips_the_check_and_the_flow_continues(env, api):
    api.script = [UnsupportedDocType("not configured in ezina_id_verify")]
    await to_passport(env)
    d = await front(env)
    assert d.name_check_status == "SKIPPED" and d.extracted_name is None and d.name_checked_at is None
    assert await env.stage() == "COLLECT_SELFIE" and "Got it" in env.graph.texts()[-1]
    assert (await draft(env))["id_front_doc"] == str(d.id)


async def test_a_not_found_result_still_asks_for_a_clearer_photo_not_a_new_file_type(env, api):
    api.default = not_found("passport")
    await to_passport(env)
    assert "clearer photo" in env.graph.texts()[-1] and M.ID_SEND_PHOTO not in env.graph.texts()[-1]


@pytest.mark.parametrize("mime", ["application/pdf", "image/webp", "image/gif"])
async def test_a_file_that_is_not_jpeg_or_png_at_the_id_step_asks_for_a_photo(env, api, mime):
    await env.run_registration_until("id_type")
    await env.document(mime=mime, data=b"%PDF-1.4 x" if mime == "application/pdf" else None)
    assert env.graph.texts()[-1].startswith(M.ID_SEND_PHOTO)
    assert [d for d in await docs(env)] == [] and api.requests == []  # nothing stored, nothing sent to the package
    assert (await draft(env))["id_attempts"] == 1 and await env.stage() == "COLLECT_ID_DOCUMENT"


@pytest.mark.parametrize("mime", ["image/jpeg", "image/png"])
async def test_a_jpeg_or_png_sent_as_a_document_is_accepted_at_the_id_step(env, api, mime):
    api.name("John")
    await env.run_registration_until("id_type")
    await env.document(mime=mime)
    assert await env.stage() == "COLLECT_SELFIE" and (await front(env)).mime_type == mime


async def test_an_id_photo_message_is_unaffected_by_the_pdf_rule(env, api):
    api.name("John")
    await to_passport(env)
    assert (await front(env)).name_check_status == "MATCHED"


async def test_admin_detail_shows_how_the_name_was_read(env, api):
    await to_passport(env)
    f = await env.farmer()
    r = await env.client.get(f"/api/admin/farmers/{f.id}", headers={"X-API-Key": ADMIN_KEY})
    (ident,) = [d for d in r.json()["identity_documents"] if d["kind"] == "ID_FRONT"]
    assert ident["name_extract_method"] == "label" and ident["name_extract_confidence"] == 0.85


async def test_the_same_photo_can_be_sent_again_after_its_name_could_not_be_read(env, api):
    photo = make_image()  # identical bytes both times (the helper makes a new random image otherwise)
    api.default = not_found("passport")
    await to_passport(env, send_photo=False)
    await env.identity_image(data=photo)
    assert "clearer photo" in env.graph.texts()[-1]
    api.default = None
    api.name("John")  # e.g. the photo is read this time
    await env.identity_image(data=photo)
    assert "already been used" not in " ".join(env.graph.texts())
    assert await env.stage() == "COLLECT_SELFIE" and (await front(env)).name_check_status == "MATCHED"
    (row,) = [d for d in await docs(env) if d.kind == "ID_FRONT"]  # the unreadable one is gone, not kept beside it
    assert row.status == "ACCEPTED"


async def test_a_photo_whose_name_was_not_found_is_deleted_from_storage_and_the_database(env, api):
    api.default = not_found("passport")
    await to_passport(env, send_photo=False)
    await env.identity_image(data=make_image())
    assert [d for d in await docs(env) if d.kind == "ID_FRONT"] == []


async def test_a_leftover_rejected_row_of_the_same_photo_does_not_block_a_resend(env, api):
    """Rows rejected before unreadable IDs were deleted still hold their hash: the farmer's own one is cleared."""
    photo = make_image()
    api.name("John")
    await to_passport(env, send_photo=False)
    farmer = await env.farmer()
    async with env.c.db.sessionmaker() as s, s.begin():
        s.add(IdentityDocument(
            farmer_id=farmer.id, country="BW", kind="ID_FRONT", id_document_type="PASSPORT", wa_media_id="OLDMEDIA",
            storage_key="identity/old/id_front/old.jpg", mime_type="image/jpeg", size_bytes=len(photo),
            sha256=hashlib.sha256(photo).hexdigest(), quality_result={}, attempt=1, status="REJECTED",
            name_check_status="NOT_FOUND"))
    await env.identity_image(data=photo)
    assert "already been used" not in " ".join(env.graph.texts())
    (row,) = [d for d in await docs(env) if d.kind == "ID_FRONT"]
    assert row.status == "ACCEPTED" and row.wa_media_id != "OLDMEDIA" and await env.stage() == "COLLECT_SELFIE"


async def test_a_photo_from_another_farmer_or_an_accepted_one_is_still_refused_as_reused(env, api):
    photo = make_image()
    api.name("John")
    await to_passport(env, send_photo=False)
    await env.identity_image(data=photo)  # accepted
    assert await env.stage() == "COLLECT_SELFIE"
    await env.identity_image(data=photo)  # the same bytes as the accepted ID, now as the selfie
    assert "already been used" in env.graph.texts()[-1]


async def test_a_name_match_is_not_announced_to_the_farmer(env, api):
    api.name("John")
    await to_passport(env)
    receipt = env.graph.texts()[-1].split("\n\n")[0]
    assert receipt == "Thank you, your ID has been received ✅."  # the plain receipt, nothing about the name or a review


def _old_id_row(farmer_id, photo: bytes, status: str, media: str = "OLDMEDIA") -> IdentityDocument:
    return IdentityDocument(
        farmer_id=farmer_id, country="BW", kind="ID_FRONT", id_document_type="PASSPORT", wa_media_id=media,
        storage_key="identity/old/id_front/old.jpg", mime_type="image/jpeg", size_bytes=len(photo),
        sha256=hashlib.sha256(photo).hexdigest(), quality_result={}, attempt=1, status=status)


async def test_an_id_photo_the_farmer_replaced_can_be_used_again(env, api):
    photo = make_image()
    api.name("John")
    await to_passport(env, send_photo=False)
    farmer = await env.farmer()
    async with env.c.db.sessionmaker() as s, s.begin():
        s.add(_old_id_row(farmer.id, photo, "SUPERSEDED"))  # e.g. replaced after [Upload another ID]
    await env.identity_image(data=photo)
    assert "already been used" not in " ".join(env.graph.texts())
    rows = [d for d in await docs(env) if d.kind == "ID_FRONT"]
    assert [d.status for d in rows] == ["ACCEPTED"] and rows[0].wa_media_id != "OLDMEDIA"  # the old row is gone
    assert await env.stage() == "COLLECT_SELFIE"


async def test_another_farmers_id_photo_is_still_refused(env, api):
    photo = make_image()
    api.name("John")
    await to_passport(env, send_photo=False)
    async with env.c.db.sessionmaker() as s, s.begin():
        s.add(_old_id_row(uuid.uuid4(), photo, "SUPERSEDED", "OTHERMEDIA"))  # another farmer's
    await env.identity_image(data=photo)
    assert "already been used" in env.graph.texts()[-1] and await env.stage() == "COLLECT_ID_DOCUMENT"


# ------------------------------------------------------------------ 9. migration 0004
def _alembic(db, *args):
    import os
    import subprocess
    import sys
    from pathlib import Path

    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db.as_posix()}"}
    root = Path(__file__).resolve().parent.parent
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=root, env=env, capture_output=True, text=True)


def _ident_cols(db) -> set[str]:
    import sqlite3

    with sqlite3.connect(db) as c:
        return {r[1] for r in c.execute("pragma table_info(identity_documents)")}


NEW_COLS = {"name_check_status", "name_match_score", "extracted_name", "name_checked_at", "name_check_attempts"}


def test_migration_0004_adds_the_name_check_columns_and_is_reversible(tmp_path):
    import sqlite3

    db = tmp_path / "old.db"
    with sqlite3.connect(db) as c:  # identity_documents as it was before the name check
        c.execute("create table identity_documents (id CHAR(32) primary key, farmer_id CHAR(32), kind varchar(10), "
                  "status varchar(12), created_at datetime, updated_at datetime)")
        c.execute("insert into identity_documents (id, kind, status) values ('a', 'ID_FRONT', 'ACCEPTED')")
    assert _alembic(db, "stamp", "0003").returncode == 0
    r = _alembic(db, "upgrade", "head")
    assert r.returncode == 0, r.stderr
    assert NEW_COLS <= _ident_cols(db)
    with sqlite3.connect(db) as c:  # existing rows keep their data; the attempt counter starts at 0
        assert c.execute("select kind, name_check_status, name_check_attempts from identity_documents").fetchall() == [("ID_FRONT", None, 0)]
    assert _alembic(db, "downgrade", "0003").returncode == 0
    assert not NEW_COLS & _ident_cols(db)


def test_migration_0004_on_a_fresh_database_is_a_no_op_after_0001(tmp_path):
    db = tmp_path / "fresh.db"
    assert _alembic(db, "upgrade", "head").returncode == 0
    assert NEW_COLS <= _ident_cols(db)
    assert _alembic(db, "upgrade", "head").returncode == 0


