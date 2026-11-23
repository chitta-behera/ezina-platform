"""ID name check: the extraction API client, the config, name matching and the farmer-facing flow.

The extraction API is mocked with httpx.MockTransport. The name read from an ID is sensitive: these tests also prove it
never reaches a log, a farmer message or a Claude prompt.
"""
from __future__ import annotations

import asyncio
import json
import logging

import httpx
import pytest

from app.config import Settings
from app.enums import Intent, NameCheckStatus
from app.models import Conversation, IdentityDocument
from app.services import name_match
from app.services.claude_service import build_user_message
from app.services.doc_extract_service import DocExtractError, DocExtractService, read_name
from app.workflows import identity_flow
from tests.conftest import ADMIN_KEY, make_ai

API_URL = "https://extract.test/extract"
ID_NAME = "Mokoena Thabo Zuma"  # a distinctive name "printed on the ID": must never leak


# ------------------------------------------------------------------ the mocked extraction API
def envelope(name: str) -> httpx.Response:
    """The real API's shape: every field is {"value", "confidence", ...} under "fields"; other fields must be ignored."""
    field = lambda v: {"value": v, "confidence": 0.98, "source": "ocr", "validation": "unchecked"}  # noqa: E731
    return httpx.Response(200, json={"fields": {
        "epic_number": field("UHN8691735"), "relation_name": field("Niranjan Behera"), "name": field(name),
        "given_names": field(name), "gender": field("Male"), "age": field(42),
    }})


class ExtractMock:
    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.script: list = []  # httpx.Response | Exception | callable, popped first
        self.default = envelope(ID_NAME)
        self.delay = 0.0

    async def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        item = self.script.pop(0) if self.script else self.default
        if isinstance(item, Exception):
            raise item
        return item

    def name(self, value: str) -> None:
        self.default = envelope(value)


def make_service(**overrides) -> tuple[DocExtractService, ExtractMock]:
    mock = ExtractMock()
    base = dict(
        _env_file=None, doc_extract_enabled=True, doc_extract_api_url=API_URL, doc_extract_retry_base_delay=0,
        doc_extract_max_retries=2,
    )
    settings = Settings(**{**base, **overrides})
    return DocExtractService(settings, client=httpx.AsyncClient(transport=httpx.MockTransport(mock.handler))), mock


@pytest.fixture
def api(env):
    """The running app with the name check switched on and the API mocked."""
    mock = ExtractMock()
    s = env.c.settings
    s.doc_extract_enabled, s.doc_extract_api_url = True, API_URL
    s.doc_extract_retry_base_delay, s.doc_extract_hold_seconds = 0, 60
    env.c.doc_extract = DocExtractService(s, client=httpx.AsyncClient(transport=httpx.MockTransport(mock.handler)))
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


# ------------------------------------------------------------------ 1. the client
async def test_request_is_multipart_with_doc_type_and_file_and_bearer_key():
    svc, mock = make_service(doc_extract_api_key="sekret-key")
    name = await svc.extract_name(doc_type="passport", name_fields=["fields.name.value"], data=b"IMGBYTES", mime="image/png")
    assert name == ID_NAME
    (req,) = mock.requests
    assert req.method == "POST" and str(req.url) == API_URL
    assert req.headers["content-type"].startswith("multipart/form-data")
    body = req.content
    assert b'name="doc_type"' in body and b"passport" in body
    assert b'name="file"; filename="id.png"' in body and b"Content-Type: image/png" in body and b"IMGBYTES" in body
    assert req.headers["authorization"] == "Bearer sekret-key"


async def test_custom_key_header_gets_the_bare_key_and_no_key_sends_no_header():
    svc, mock = make_service(doc_extract_api_key="k1", doc_extract_api_key_header="X-Api-Key")
    await svc.extract_name(doc_type="pan", name_fields=["given_names"], data=b"x", mime="image/jpeg")
    assert mock.requests[0].headers["x-api-key"] == "k1" and "authorization" not in mock.requests[0].headers
    svc2, mock2 = make_service()
    await svc2.extract_name(doc_type="pan", name_fields=["given_names"], data=b"x", mime="application/pdf")
    assert "authorization" not in mock2.requests[0].headers and b'filename="id.pdf"' in mock2.requests[0].content


@pytest.mark.parametrize("payload,fields,expected", [
    ({"given_names": "Thabo", "surname": "Mokoena"}, ["given_names", "surname"], "Thabo Mokoena"),  # passport
    ({"given_names": "Thabo", "surname": ""}, ["given_names", "surname"], "Thabo"),  # only given names
    ({"given_names": "Thabo"}, ["given_names", "surname"], "Thabo"),  # surname missing
    ({"name": "RAJESH KUMAR", "pan": "ABCDE1234F"}, ["name"], "RAJESH KUMAR"),  # PAN: id number is ignored
    ({"name": "Asha Devi", "epic_no": "XYZ123"}, ["name"], "Asha Devi"),  # voter id
    ({"data": {"name": "Wrapped Name"}}, ["data.name"], "Wrapped Name"),  # nested path
    ({"fields": {"name": {"value": "Chittaranjan Behera", "confidence": 0.98}, "relation_name": {"value": "Niranjan Behera"},
                 "epic_number": {"value": "UHN8691735"}, "age": {"value": 42}}}, ["fields.name.value"], "Chittaranjan Behera"),
    ({"fields": {"given_names": {"value": "Thabo"}, "surname": {"value": "Mokoena"}}},
     ["fields.given_names.value", "fields.surname.value"], "Thabo Mokoena"),
    ({"fields": {"name": {"value": None, "confidence": 0.1}}}, ["fields.name.value"], None),  # nothing read
    ({"data": {"a": "A", "b": {"c": "C"}}}, ["data.a", "data.b.c"], "A C"),
    ({"data": None}, ["data.name"], None),
    ({"other": "x"}, ["name"], None),  # none of the fields present
    ({"name": "   "}, ["name"], None),  # all empty
    ({"name": 12345}, ["name"], None),  # not text
    (["not", "an", "object"], ["name"], None),
])
def test_read_name_joins_the_configured_fields_in_order(payload, fields, expected):
    assert read_name(payload, fields) == expected


async def test_5xx_is_retried_then_succeeds():
    svc, mock = make_service()
    mock.script = [httpx.Response(503), httpx.Response(502), httpx.Response(200, json={"name": "Asha"})]
    assert await svc.extract_name(doc_type="pan", name_fields=["name"], data=b"x", mime="image/jpeg") == "Asha"
    assert len(mock.requests) == 3


async def test_timeouts_and_connection_errors_are_retried_then_raise():
    svc, mock = make_service()
    mock.script = [httpx.ReadTimeout("slow"), httpx.ConnectError("down"), httpx.ConnectTimeout("slow")]
    with pytest.raises(DocExtractError):
        await svc.extract_name(doc_type="pan", name_fields=["name"], data=b"x", mime="image/jpeg")
    assert len(mock.requests) == 3  # 1 try + DOC_EXTRACT_MAX_RETRIES


async def test_persistent_5xx_raises_after_the_retries():
    svc, mock = make_service(doc_extract_max_retries=1)
    mock.default = httpx.Response(500)
    with pytest.raises(DocExtractError) as e:
        await svc.extract_name(doc_type="pan", name_fields=["name"], data=b"x", mime="image/jpeg")
    assert e.value.reason == "http_500" and len(mock.requests) == 2


@pytest.mark.parametrize("response", [httpx.Response(400), httpx.Response(401), httpx.Response(422),
                                      httpx.Response(200, content=b"<html>not json</html>")])
async def test_4xx_and_unparseable_bodies_are_not_retried(response):
    svc, mock = make_service()
    mock.script = [response]
    with pytest.raises(DocExtractError):
        await svc.extract_name(doc_type="pan", name_fields=["name"], data=b"x", mime="image/jpeg")
    assert len(mock.requests) == 1


async def test_client_logs_status_and_timing_but_never_the_name_or_id_fields(caplog):
    svc, mock = make_service()
    with caplog.at_level(logging.DEBUG, logger="ezina"):
        await svc.extract_name(doc_type="passport", name_fields=["given_names"], data=b"x", mime="image/jpeg")
    assert "doc extract call" in caplog.text
    for secret in (ID_NAME, "UHN8691735", "Niranjan Behera"):
        assert secret not in app_log_text(caplog)


# ------------------------------------------------------------------ 2. per-document configuration
def test_configured_id_types_and_those_without_configuration():
    assert identity_flow.extraction_for("PASSPORT").doc_type == "passport"
    assert identity_flow.extraction_for("PASSPORT").name_fields == ("fields.given_names.value", "fields.surname.value")
    assert identity_flow.extraction_for("PAN").name_fields == ("fields.name.value",)
    assert identity_flow.extraction_for("VOTER_ID").name_fields == ("fields.name.value",)
    assert identity_flow.extraction_for("VOTER_ID").doc_type == "voter_id"
    assert identity_flow.extraction_for("AADHAAR_MASKED").doc_type == "aadhaar"
    assert identity_flow.extraction_for("AADHAAR_MASKED").name_fields == ("fields.name.value",)
    for code in ("DRIVING_LICENCE", "OMANG", "KCC", None, "NOPE"):
        assert identity_flow.extraction_for(code) is None


GOOD = """
countries:
  BW:
    types:
      - {code: PASSPORT, names: {en: "Passport"}}
      - {code: OMANG, names: {en: "Omang"}}
extraction:
  PASSPORT: {doc_type: passport, name_fields: [given_names, surname]}
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
    config_file.write_text(GOOD.replace("extraction:", "extraction:\n  OMANG: {doc_type: omang, name_fields: [data.full_name]}"))
    identity_flow.validate_config()
    spec = identity_flow.extraction_for("OMANG")
    assert (spec.doc_type, spec.name_fields) == ("omang", ("data.full_name",))


@pytest.mark.parametrize("bad,message", [
    ("just: a mapping", "'countries'"),
    (GOOD.replace("doc_type: passport, ", ""), "extraction.PASSPORT: 'doc_type'"),
    (GOOD.replace("[given_names, surname]", "[]"), "extraction.PASSPORT: 'name_fields'"),
    (GOOD.replace("[given_names, surname]", "given_names"), "extraction.PASSPORT: 'name_fields'"),
    (GOOD.replace("[given_names, surname]", "[given_names, '']"), "extraction.PASSPORT: 'name_fields'"),
    (GOOD.replace("PASSPORT: {doc", "GHOST: {doc"), "'GHOST' is not an ID type"),
    (GOOD.replace("extraction:\n  PASSPORT: {doc_type: passport, name_fields: [given_names, surname]}", "extraction: [1, 2]"), "'extraction' must be a mapping"),
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


# ------------------------------------------------------------------ 3. name matching
@pytest.mark.parametrize("given,on_id", [
    ("John Mokoena", "John Mokoena"),
    ("John Mokoena", "MOKOENA JOHN"),  # word order
    ("John Mokoena", "John Peter Mokoena"),  # middle name
    ("J. Mokoena", "John Mokoena"),  # initial
    ("John M", "John Mokoena"),  # initial as surname
    ("John Mokoena", "J P Mokoena"),  # initials on the ID side
    ("Mr John Mokoena", "John Mokoena"),  # titles
    ("Shri Rajesh Kumar", "Rajesh Kumar"),
    ("Smt. Asha Devi", "ASHA DEVI"),
    ("José Müller", "Jose Muller"),  # accents
    ("Amélie O'Neil", "Amelie ONeil"),  # punctuation
    ("John Mokoena", "Jon Mokoena"),  # minor typo
    ("Thabo Mokoena", "Thabo Mokoenaa"),
])
def test_names_that_should_match(given, on_id):
    status, s = name_match.compare(given, on_id)
    assert status == NameCheckStatus.MATCHED, (given, on_id, s)


@pytest.mark.parametrize("given,on_id", [
    ("John Mokoena", "Peter Dlamini"),
    ("John Mokoena", "John Dlamini"),  # same first name only
    ("John", "John Mokoena"),  # a lone given name must not match any longer name
    ("A. Mokoena", "John Mokoena"),  # wrong initial
])
def test_names_that_should_not_match(given, on_id):
    status, _ = name_match.compare(given, on_id)
    assert status in (NameCheckStatus.PARTIAL, NameCheckStatus.MISMATCH)


def test_thresholds_and_not_found():
    assert name_match.compare("John", "Jonn", threshold=99, partial=75)[0] == NameCheckStatus.PARTIAL
    assert name_match.compare("John", "Jonn", threshold=99, partial=95)[0] == NameCheckStatus.MISMATCH
    assert name_match.compare("John Mokoena", "")[0] == NameCheckStatus.NOT_FOUND
    assert name_match.compare("John Mokoena", None) == (NameCheckStatus.NOT_FOUND, 0.0)
    assert name_match.compare("", "John Mokoena")[0] == NameCheckStatus.MISMATCH


def test_normalise():
    assert name_match.normalise("  Dr.  JOSÉ   o'Neil-Smith ") == "jose o neil smith"


# ------------------------------------------------------------------ 4. flow: no API call
async def test_id_type_without_configuration_skips_the_check(env, api):
    await env.run_registration_until("id_front")  # Omang: not configured
    assert api.requests == []
    d = await front(env)
    assert d.name_check_status == "SKIPPED" and d.extracted_name is None
    assert await env.stage() == "COLLECT_SELFIE" and "Got it" in env.graph.texts()[-1]


async def test_disabled_makes_no_api_call(env, api):
    env.c.settings.doc_extract_enabled = False
    await to_passport(env)
    assert api.requests == []
    assert (await front(env)).name_check_status == "SKIPPED" and await env.stage() == "COLLECT_SELFIE"


async def test_selfie_and_id_back_never_call_the_api(env, api):
    api.name("John")
    await to_passport(env)
    assert len(api.requests) == 1
    await env.identity_image()  # the selfie
    assert len(api.requests) == 1


# ------------------------------------------------------------------ 5. flow: results
async def test_matched_continues_and_stores_the_result(env, api):
    api.name("John")
    await to_passport(env)
    (req,) = api.requests
    assert b'name="doc_type"' in req.content and b"passport" in req.content and b'filename="id.jpg"' in req.content
    d = await front(env)
    assert d.name_check_status == "MATCHED" and float(d.name_match_score) == 100.0 and d.extracted_name == "John"
    assert d.name_checked_at is not None and d.name_check_attempts == 0
    assert await env.stage() == "COLLECT_SELFIE" and "ID has been received" in env.graph.texts()[-1]
    assert (await draft(env))["id_front_doc"] == str(d.id)


async def test_mismatch_offers_the_two_buttons_and_does_not_repeat_the_name_on_the_id(env, api):
    await to_passport(env)  # the ID says "Mokoena Thabo Zuma", the farmer said "John"
    msg = env.graph.texts()[-1]
    assert msg == "The name on your ID doesn't match the name you gave us (John). Please choose an option:"
    assert env.graph.last_buttons() == ["name_change", "id_reupload"]
    for fragment in ("Mokoena", "Thabo", "Zuma", "UHN8691735"):
        assert fragment not in " ".join(env.graph.texts())
    d = await front(env)
    assert d.name_check_status == "MISMATCH" and d.name_check_attempts == 1 and d.status == "ACCEPTED"
    dr = await draft(env)
    assert dr["name_choice_pending"] and dr["id_front_doc"] is None and await env.stage() == "COLLECT_ID_DOCUMENT"


async def test_partial_is_treated_like_a_mismatch(env, api):
    env.c.settings.name_match_threshold = 99
    api.name("Jonn")
    await to_passport(env)
    assert (await front(env)).name_check_status == "PARTIAL"
    assert env.graph.last_buttons() == ["name_change", "id_reupload"]


async def test_not_found_asks_for_a_clearer_photo_and_counts_as_an_attempt(env, api):
    api.default = httpx.Response(200, json={"other": "nothing useful"})
    await to_passport(env)
    assert "clearer photo" in env.graph.texts()[-1]
    d = await front(env)
    assert d.name_check_status == "NOT_FOUND" and d.status == "REJECTED"
    assert (await draft(env))["id_attempts"] == 1 and await env.stage() == "COLLECT_ID_DOCUMENT"
    await env.identity_image()
    await env.identity_image()  # third failed attempt (IDENTITY_MAX_ATTEMPTS)
    dr = await draft(env)
    assert dr["id_needs_help"] and await env.stage() == "COLLECT_SELFIE"


@pytest.mark.parametrize("failure,calls", [
    (httpx.Response(500), 3), (httpx.ReadTimeout("slow"), 3), (httpx.Response(401), 1),
])
async def test_api_failure_does_not_block_the_farmer(env, api, failure, calls):
    api.script = [failure] * 3
    await to_passport(env)
    assert len(api.requests) == calls
    d = await front(env)
    assert d.name_check_status == "ERROR" and d.extracted_name is None and d.name_checked_at is not None
    assert await env.stage() == "COLLECT_SELFIE"
    assert "doesn't match" not in " ".join(env.graph.texts()) and "Got it" in env.graph.texts()[-1]
    assert (await draft(env))["id_front_doc"] == str(d.id)


async def test_holding_message_when_the_check_is_slow(env, api):
    env.c.settings.doc_extract_hold_seconds = 0.05
    api.delay, api.default = 0.3, envelope("John")
    await to_passport(env)
    texts = env.graph.texts()
    assert "Checking your ID, please wait a moment…" in texts
    assert texts.index("Checking your ID, please wait a moment…") < len(texts) - 1  # before the real reply
    assert (await front(env)).name_check_status == "MATCHED"


async def test_no_holding_message_when_the_check_is_quick(env, api):
    api.name("John")
    await to_passport(env)
    assert not any("Checking your ID" in t for t in env.graph.texts())


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
    assert (await docs(env, IdentityDocument.id == first.id))[0].status == "SUPERSEDED"
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
    assert (await docs(env, IdentityDocument.id == first.id))[0].status == "SUPERSEDED"
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
_STD_RECORD_FIELDS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}  # timing floats are noise


def app_log_text(caplog) -> str:
    """Everything the app itself logged (message and structured fields); SQL driver debug output is not ours."""
    return " ".join(
        f"{r.getMessage()} {sorted((k, v) for k, v in r.__dict__.items() if k not in _STD_RECORD_FIELDS)}"
        for r in caplog.records if r.name.startswith("ezina")
    )


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


def test_masked_aadhaar_is_name_checked_with_the_apis_aadhaar_doc_type():
    spec = identity_flow.extraction_for("AADHAAR_MASKED")
    assert spec is not None and spec.doc_type == "aadhaar" and spec.name_fields == ("fields.name.value",)
