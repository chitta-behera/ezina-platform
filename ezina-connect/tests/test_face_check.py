"""Selfie face check: the face-verification API client, how Python reads its result, and the farmer-facing flow.

The API is mocked with httpx.MockTransport. The scores are for the operations team only: these tests also prove they
never reach a farmer message, a log line or a Claude prompt, and that the check never verifies a farmer.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os

import httpx
import pytest
from PIL import Image

from app.config import Settings
from app.enums import FaceCheckStatus, Intent
from app.models import Conversation, IdentityDocument
from app.services.claude_service import build_user_message
from app.services.doc_extract_service import DocExtractService
from app.services.face_verify_service import (
    FaceResult,
    FaceVerifyError,
    FaceVerifyService,
    classify,
    parse_result,
)
from app.schemas.conversation import Draft
from app.workflows import reply_guard
from tests.conftest import ADMIN_KEY, make_ai

API_URL = "https://face.test/verify"
SCORE = "0.9673"  # the distance in the sample response: must never reach the farmer


def result(**over) -> dict:
    base = {
        "verified": False, "distance": 0.9673, "threshold": 0.68, "confidence_band": "no_match",
        "liveness_passed": True, "face_found_id": True, "face_found_selfie": True, "model": "ArcFace",
        "detector": "retinaface", "processing_ms": 13800.2, "error": None, "warnings": [],
    }
    return {**base, **over}


def reply(**over) -> httpx.Response:
    return httpx.Response(200, json=result(**over))


class FaceMock:
    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.script: list = []  # httpx.Response | Exception, popped first
        self.default = reply()
        self.delay = 0.0

    async def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        item = self.script.pop(0) if self.script else self.default
        if isinstance(item, Exception):
            raise item
        return item

    def verdict(self, **over) -> None:
        self.default = reply(**over)


def make_service(**overrides) -> tuple[FaceVerifyService, FaceMock]:
    mock = FaceMock()
    base = dict(_env_file=None, face_verify_enabled=True, face_verify_api_url=API_URL, face_verify_retry_base_delay=0,
                face_verify_max_retries=2)
    settings = Settings(**{**base, **overrides})
    return FaceVerifyService(settings, client=httpx.AsyncClient(transport=httpx.MockTransport(mock.handler))), mock


async def call(svc: FaceVerifyService, **kw) -> FaceResult:
    args = dict(id_image=b"IDBYTES", id_mime="image/png", selfie_image=b"SELFIEBYTES", selfie_mime="image/jpeg")
    return await svc.verify(**{**args, **kw})


@pytest.fixture
def face(env):
    """The running app with the face check switched on and the API mocked (a mismatch by default)."""
    mock = FaceMock()
    s = env.c.settings
    s.face_verify_enabled, s.face_verify_api_url, s.face_verify_retry_base_delay = True, API_URL, 0
    env.c.face_verify = FaceVerifyService(s, client=httpx.AsyncClient(transport=httpx.MockTransport(mock.handler)))
    return mock


async def draft(env) -> dict:
    return (await env.conv()).draft


async def rows(env, kind: str) -> list[IdentityDocument]:
    return sorted([d for d in await env.all(IdentityDocument) if d.kind == kind], key=lambda d: d.created_at)


async def to_selfie(env):
    """Registration up to the selfie step (a Botswana Omang ID has been accepted)."""
    await env.run_registration_until("id_front")
    assert await env.stage() == "COLLECT_SELFIE"


async def with_selfie(env):
    await to_selfie(env)
    await env.identity_image()


_STD_RECORD_FIELDS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}  # timing floats are noise


def app_log_text(caplog) -> str:
    return " ".join(
        f"{r.getMessage()} {sorted((k, v) for k, v in r.__dict__.items() if k not in _STD_RECORD_FIELDS)}"
        for r in caplog.records if r.name.startswith("ezina")
    )


def real_pdf() -> bytes:
    buf = io.BytesIO()
    Image.frombytes("RGB", (16, 16), os.urandom(768)).resize((800, 800)).save(buf, format="PDF")
    return buf.getvalue()


# ------------------------------------------------------------------ 1. the client
async def test_request_is_multipart_with_both_images_content_types_and_bearer_key():
    svc, mock = make_service(face_verify_api_key="sekret-key")
    r = await call(svc)
    assert r.verified is False
    (req,) = mock.requests
    assert req.method == "POST" and str(req.url) == API_URL
    assert req.headers["content-type"].startswith("multipart/form-data")
    body = req.content
    assert b'name="id_image"; filename="id.png"' in body and b"IDBYTES" in body
    assert b'name="selfie_image"; filename="selfie.jpg"' in body and b"SELFIEBYTES" in body
    assert b"Content-Type: image/png" in body and b"Content-Type: image/jpeg" in body
    assert req.headers["authorization"] == "Bearer sekret-key"


async def test_custom_key_header_gets_the_bare_key_and_no_key_sends_no_header():
    svc, mock = make_service(face_verify_api_key="k1", face_verify_api_key_header="X-Api-Key")
    await call(svc)
    assert mock.requests[0].headers["x-api-key"] == "k1" and "authorization" not in mock.requests[0].headers
    svc2, mock2 = make_service()
    await call(svc2)
    assert "authorization" not in mock2.requests[0].headers


async def test_the_sample_response_is_parsed_field_by_field():
    svc, _ = make_service()
    r = await call(svc)
    assert (r.verified, r.distance, r.threshold, r.confidence_band) == (False, 0.9673, 0.68, "no_match")
    assert (r.liveness_passed, r.face_found_id, r.face_found_selfie) == (True, True, True)
    assert (r.model, r.detector, r.processing_ms, r.error, r.warnings) == ("ArcFace", "retinaface", 13800.2, None, [])


def test_extra_unknown_fields_and_missing_optional_fields_still_parse():
    r = parse_result({"verified": True, "brand_new_field": {"x": 1}, "another": [1, 2]})
    assert r.verified is True and r.distance is None and r.warnings == [] and r.face_found_id is None
    assert classify(r) == FaceCheckStatus.MATCHED
    r2 = parse_result({"verified": False, "warnings": ["blurry", 3], "distance": "not a number", "error": ""})
    assert r2.warnings == ["blurry", "3"] and r2.distance is None and r2.error is None
    with pytest.raises(FaceVerifyError):
        parse_result(["not", "an", "object"])


# ------------------------------------------------------------------ 2. how Python reads the result
@pytest.mark.parametrize("over,expected", [
    ({"verified": True}, FaceCheckStatus.MATCHED),
    ({"verified": False}, FaceCheckStatus.MISMATCH),
    ({"face_found_id": False}, FaceCheckStatus.NO_FACE_ID),
    ({"face_found_selfie": False}, FaceCheckStatus.NO_FACE_SELFIE),
    ({"liveness_passed": False}, FaceCheckStatus.LIVENESS_FAILED),
    ({"error": "no face detected"}, FaceCheckStatus.ERROR),
    # the order: error, no face in the ID, no face in the selfie, liveness, then verified / not verified
    ({"error": "x", "verified": True}, FaceCheckStatus.ERROR),
    ({"error": "x", "liveness_passed": False}, FaceCheckStatus.ERROR),
    # this API explains "no face found" in `error`: an explicit no-face flag is a definite result, not an API failure
    ({"error": "no face found in ID photo", "face_found_id": False, "face_found_selfie": False}, FaceCheckStatus.NO_FACE_ID),
    ({"error": "no face found in selfie", "face_found_selfie": False}, FaceCheckStatus.NO_FACE_SELFIE),
    ({"face_found_id": False, "face_found_selfie": False, "liveness_passed": False}, FaceCheckStatus.NO_FACE_ID),
    ({"face_found_selfie": False, "liveness_passed": False, "verified": True}, FaceCheckStatus.NO_FACE_SELFIE),
    ({"liveness_passed": False, "verified": True}, FaceCheckStatus.LIVENESS_FAILED),
])
def test_classify_follows_the_documented_order(over, expected):
    assert classify(parse_result(result(**over))) == expected


def test_a_response_with_no_verdict_is_an_error():
    assert classify(parse_result({"model": "ArcFace"})) == FaceCheckStatus.ERROR
    assert classify(parse_result({"verified": "yes"})) == FaceCheckStatus.ERROR  # not a boolean


# ------------------------------------------------------------------ 3. retries
async def test_5xx_is_retried_then_succeeds():
    svc, mock = make_service()
    mock.script = [httpx.Response(503), httpx.Response(502), reply(verified=True)]
    assert (await call(svc)).verified is True and len(mock.requests) == 3


async def test_timeouts_and_connection_errors_are_retried_then_raise():
    svc, mock = make_service()
    mock.script = [httpx.ReadTimeout("slow"), httpx.ConnectError("down"), httpx.ConnectTimeout("slow")]
    with pytest.raises(FaceVerifyError):
        await call(svc)
    assert len(mock.requests) == 3  # 1 try + FACE_VERIFY_MAX_RETRIES


@pytest.mark.parametrize("response", [httpx.Response(400), httpx.Response(401), httpx.Response(422),
                                      httpx.Response(200, content=b"<html>not json</html>"),
                                      httpx.Response(200, json=["not", "an", "object"])])
async def test_4xx_and_unparseable_bodies_are_not_retried(response):
    svc, mock = make_service()
    mock.script = [response]
    with pytest.raises(FaceVerifyError):
        await call(svc)
    assert len(mock.requests) == 1


async def test_client_logs_status_and_timing_but_never_scores_or_images(caplog):
    svc, _ = make_service()
    with caplog.at_level(logging.DEBUG, logger="ezina"):
        await call(svc)
    assert "face verify call" in caplog.text
    text = app_log_text(caplog)
    for secret in (SCORE, "IDBYTES", "SELFIEBYTES"):
        assert secret not in text


async def test_a_4xx_with_a_result_body_is_a_result_not_a_failure():
    """The real API answers "no face found" with HTTP 422 and the normal result body."""
    svc, mock = make_service()
    mock.script = [httpx.Response(422, json=result(
        verified=False, distance=None, face_found_id=False, face_found_selfie=False, error="no face found in ID photo"))]
    r = await call(svc)
    assert len(mock.requests) == 1 and r.error == "no face found in ID photo" and classify(r) == FaceCheckStatus.NO_FACE_ID


async def test_the_apis_quality_gate_answer_keeps_its_reasons_for_operations():
    """The real API answers 422 {"error": "image quality check failed", "issues": [...]} for soft (WhatsApp) photos."""
    svc, mock = make_service()
    mock.script = [httpx.Response(422, json={"error": "image quality check failed", "issues": [
        "ID photo is too blurry (sharpness 18.5 < 25.0)", "selfie is too blurry (sharpness 18.4 < 60.0)"]})]
    r = await call(svc)
    assert len(mock.requests) == 1 and classify(r) == FaceCheckStatus.ERROR
    assert r.error == ("image quality check failed: ID photo is too blurry (sharpness 18.5 < 25.0); "
                       "selfie is too blurry (sharpness 18.4 < 60.0)")


def photo(seed: int, size=(640, 480)) -> bytes:
    import random

    rnd = random.Random(seed)
    im = Image.new("RGB", size)
    px = im.load()
    for x in range(0, size[0], 8):
        for y in range(0, size[1], 8):
            c = (rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
            for i in range(8):
                for j in range(8):
                    if x + i < size[0] and y + j < size[1]:
                        px[x + i, y + j] = c
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=70)
    return buf.getvalue()


BLUR_SELFIE = {"error": "image quality check failed", "issues": ["selfie is too blurry (sharpness 18.4 < 60.0)"]}
BLUR_BOTH = {"error": "image quality check failed", "issues": [
    "ID photo is too blurry (sharpness 18.5 < 25.0)", "selfie is too blurry (sharpness 18.4 < 60.0)"]}


def part(req: httpx.Request, name: str) -> bytes:
    """The bytes of one multipart file field."""
    marker = f'name="{name}"'.encode()
    start = req.content.index(b"\r\n\r\n", req.content.index(marker)) + 4
    return req.content[start:req.content.index(b"\r\n--", start)]


async def test_a_too_blurry_rejection_is_retried_once_with_only_that_photo_sharpened():
    svc, mock = make_service()
    id_jpg, selfie_jpg = photo(1), photo(2)
    mock.script = [httpx.Response(422, json=BLUR_SELFIE), reply(verified=True, distance=0.3)]
    r = await call(svc, id_image=id_jpg, id_mime="image/jpeg", selfie_image=selfie_jpg, selfie_mime="image/jpeg")
    assert r.verified is True and len(mock.requests) == 2
    first, second = mock.requests
    assert part(first, "selfie_image") == selfie_jpg and part(first, "id_image") == id_jpg
    assert part(second, "id_image") == id_jpg  # the ID was not flagged: sent as it was
    assert part(second, "selfie_image") != selfie_jpg and part(second, "selfie_image")[:2] == b"\xff\xd8"  # a sharpened JPEG


async def test_both_photos_flagged_are_both_sharpened_and_a_png_is_sent_as_jpeg():
    svc, mock = make_service()
    buf = io.BytesIO()
    Image.open(io.BytesIO(photo(3))).save(buf, format="PNG")
    png = buf.getvalue()
    mock.script = [httpx.Response(422, json=BLUR_BOTH), reply(verified=True)]
    await call(svc, id_image=png, id_mime="image/png", selfie_image=photo(4), selfie_mime="image/jpeg")
    second = mock.requests[1].content
    assert part(mock.requests[1], "id_image") != png and b'filename="id.jpg"' in second and b"Content-Type: image/png" not in second


async def test_the_sharpen_retry_happens_only_once_and_a_second_blur_is_an_error():
    svc, mock = make_service()
    mock.script = [httpx.Response(422, json=BLUR_SELFIE), httpx.Response(422, json=BLUR_SELFIE)]
    r = await call(svc, id_image=photo(5), id_mime="image/jpeg", selfie_image=photo(6), selfie_mime="image/jpeg")
    assert len(mock.requests) == 2 and classify(r) == FaceCheckStatus.ERROR and "too blurry" in r.error


async def test_the_sharpen_retry_can_be_switched_off_and_other_rejections_do_not_trigger_it():
    svc, mock = make_service(face_verify_sharpen_retry=False)
    mock.script = [httpx.Response(422, json=BLUR_SELFIE)]
    r = await call(svc, id_image=photo(5), id_mime="image/jpeg", selfie_image=photo(6), selfie_mime="image/jpeg")
    assert len(mock.requests) == 1 and classify(r) == FaceCheckStatus.ERROR
    svc2, mock2 = make_service()
    mock2.script = [httpx.Response(422, json={"error": "image quality check failed", "issues": ["selfie is too dark"]})]
    await call(svc2, id_image=photo(5), id_mime="image/jpeg", selfie_image=photo(6), selfie_mime="image/jpeg")
    assert len(mock2.requests) == 1
    svc3, mock3 = make_service()  # a good photo is never touched
    await call(svc3, id_image=photo(5), id_mime="image/jpeg", selfie_image=photo(6), selfie_mime="image/jpeg")
    assert len(mock3.requests) == 1


async def test_an_unreadable_image_keeps_the_first_result_instead_of_failing():
    svc, mock = make_service()
    mock.script = [httpx.Response(422, json=BLUR_SELFIE)]
    r = await call(svc)  # SELFIEBYTES is not an image Pillow can read
    assert len(mock.requests) == 1 and classify(r) == FaceCheckStatus.ERROR


async def test_a_blurry_whatsapp_selfie_ends_matched_after_the_sharpen_retry_in_the_flow(env, face):
    face.script = [httpx.Response(422, json=BLUR_SELFIE), reply(verified=True)]
    await with_selfie(env)
    assert len(face.requests) == 2 and await env.stage() == "COLLECT_FARM_PHOTOS"
    (selfie,) = await rows(env, "SELFIE")
    assert selfie.face_check_status == "MATCHED"
    assert "couldn't finish" not in env.graph.texts()[-1]


async def test_a_real_validation_4xx_fails_with_the_field_names_but_no_values():
    svc, mock = make_service()
    mock.script = [httpx.Response(422, json={"detail": [
        {"loc": ["body", "id_image"], "msg": "Field required", "type": "missing", "input": None},
        {"loc": ["body", "selfie_image"], "msg": "Field required", "type": "missing", "input": "SECRETVALUE"}]})]
    with pytest.raises(FaceVerifyError) as e:
        await call(svc)
    assert e.value.reason == "http_422 body.id_image: Field required; body.selfie_image: Field required"
    assert "SECRETVALUE" not in e.value.reason and len(mock.requests) == 1


# ------------------------------------------------------------------ 4. flow: results
async def test_mismatch_offers_two_buttons_with_tips_and_shows_no_score(env, face):
    await with_selfie(env)
    texts = env.graph.texts()
    assert "Checking your selfie" in " ".join(texts)  # the API is slow: the holding message comes first
    msg = texts[-1]
    assert msg.startswith("Your selfie doesn't seem to match the photo on your ID. Please choose an option:")
    assert "face the light" in msg and "no cap or sunglasses" in msg
    assert env.graph.last_buttons() == ["selfie_new", "id_reupload"]
    for secret in (SCORE, "0.68", "ArcFace", "no_match"):
        assert secret not in " ".join(texts)
    (selfie,) = await rows(env, "SELFIE")
    (id_front,) = await rows(env, "ID_FRONT")
    assert selfie.face_check_status == "MISMATCH" and selfie.face_verified is False
    assert float(selfie.face_distance) == 0.9673 and float(selfie.face_threshold) == 0.68
    assert (selfie.face_confidence_band, selfie.face_model, selfie.face_detector) == ("no_match", "ArcFace", "retinaface")
    assert selfie.face_liveness_passed and selfie.face_found_id and selfie.face_found_selfie
    assert float(selfie.face_processing_ms) == 13800.2 and selfie.face_warnings is None and selfie.face_error_message is None
    assert selfie.face_compared_id_document_id == id_front.id and selfie.face_check_attempts == 1
    assert selfie.face_checked_at is not None and selfie.status == "ACCEPTED"
    dr = await draft(env)
    assert dr["face_choice_pending"] and dr["selfie_doc"] is None and await env.stage() == "COLLECT_SELFIE"
    assert id_front.face_check_status is None  # the face check lives on the selfie row only


async def test_the_request_carries_the_stored_id_front_and_selfie(env, face):
    await to_selfie(env)
    (id_front,) = await rows(env, "ID_FRONT")
    await env.identity_image()
    (req,) = face.requests
    stored = await env.c.identity.storage.get(id_front.storage_key)
    (selfie,) = await rows(env, "SELFIE")
    stored_selfie = await env.c.identity.storage.get(selfie.storage_key)
    assert stored in req.content and stored_selfie in req.content
    assert b'name="id_image"; filename="id.jpg"' in req.content and b'name="selfie_image"; filename="selfie.jpg"' in req.content


async def test_matched_continues_and_marks_the_selfie_received(env, face):
    face.verdict(verified=True, distance=0.31, confidence_band="strong_match")
    await with_selfie(env)
    assert env.graph.texts()[-1].startswith("Thank you, your selfie has been received ✅.")
    assert await env.stage() == "COLLECT_FARM_PHOTOS"
    (selfie,) = await rows(env, "SELFIE")
    assert selfie.face_check_status == "MATCHED" and selfie.face_verified is True and selfie.face_check_attempts == 0
    assert (await draft(env))["selfie_doc"] == str(selfie.id)
    assert "0.31" not in " ".join(env.graph.texts())


async def test_no_face_in_the_id_asks_for_a_clearer_id_photo_and_supersedes_the_id(env, face):
    face.verdict(face_found_id=False, verified=False)
    await with_selfie(env)
    assert "photo on your ID isn't clear" in env.graph.texts()[-1]
    (id_front,) = await rows(env, "ID_FRONT")
    (selfie,) = await rows(env, "SELFIE")
    assert id_front.status == "SUPERSEDED" and selfie.face_check_status == "NO_FACE_ID" and selfie.status == "ACCEPTED"
    dr = await draft(env)
    assert dr["id_front_doc"] is None and dr["selfie_doc"] == str(selfie.id) and dr["face_check_attempts"] == 1
    assert await env.stage() == "COLLECT_ID_DOCUMENT"
    face.verdict(verified=True)  # the new ID: the check runs again with it and the selfie already on file
    await env.identity_image()
    assert len(face.requests) == 2 and await env.stage() == "COLLECT_FARM_PHOTOS"
    new_id = (await rows(env, "ID_FRONT"))[-1]
    assert new_id.status == "ACCEPTED"
    (selfie,) = await rows(env, "SELFIE")
    assert selfie.face_check_status == "MATCHED" and selfie.face_compared_id_document_id == new_id.id


async def test_the_apis_422_no_face_answer_asks_for_a_clearer_id_photo(env, face):
    face.script = [httpx.Response(422, json=result(
        verified=False, distance=None, face_found_id=False, face_found_selfie=False, error="no face found in ID photo"))]
    await with_selfie(env)
    assert "photo on your ID isn't clear" in env.graph.texts()[-1] and len(face.requests) == 1
    (selfie,) = await rows(env, "SELFIE")
    assert selfie.face_check_status == "NO_FACE_ID" and selfie.face_error_message == "no face found in ID photo"
    assert "no face found" not in " ".join(env.graph.texts())  # the API's wording is for operations, not the farmer


@pytest.mark.parametrize("over,status", [({"face_found_selfie": False}, "NO_FACE_SELFIE"),
                                         ({"liveness_passed": False}, "LIVENESS_FAILED")])
async def test_unusable_selfie_asks_for_a_new_one_with_a_new_challenge(env, face, over, status):
    face.verdict(**over)
    await to_selfie(env)
    old = (await draft(env))["selfie_challenge"]
    await env.identity_image()
    msg = env.graph.texts()[-1]
    assert "take a new selfie now with your front camera" in msg and "finger" in msg
    assert "selfie_new" not in env.graph.last_buttons()  # no choice to make: just a new selfie
    (selfie,) = await rows(env, "SELFIE")
    assert selfie.face_check_status == status and selfie.status == "REJECTED"
    dr = await draft(env)
    assert dr["selfie_doc"] is None and dr["selfie_challenge"] != old and await env.stage() == "COLLECT_SELFIE"
    face.verdict(verified=True)
    await env.identity_image()
    assert await env.stage() == "COLLECT_FARM_PHOTOS"


@pytest.mark.parametrize("failure,calls", [
    (reply(error="no face detected"), 1), (httpx.Response(500), 3), (httpx.ReadTimeout("slow"), 3), (httpx.Response(401), 1),
    (httpx.Response(200, content=b"not json"), 1), (reply(verified=None), 1),
])
async def test_api_failure_or_error_field_does_not_block_the_farmer(env, face, failure, calls):
    face.script = [failure] * 3
    await with_selfie(env)
    assert len(face.requests) == calls
    (selfie,) = await rows(env, "SELFIE")
    assert selfie.face_check_status == "ERROR" and selfie.face_checked_at is not None
    assert await env.stage() == "COLLECT_FARM_PHOTOS" and (await draft(env))["selfie_doc"] == str(selfie.id)
    last = env.graph.texts()[-1]  # the farmer is told the check is pending, and nothing else about it
    assert last.startswith("Thank you, your selfie has been received") and "couldn't finish the automatic photo check" in last
    assert "Ezina team will complete the check" in last
    joined = " ".join(env.graph.texts()).lower()
    assert "match" not in joined.replace("checking", "") and "401" not in joined and "http_" not in joined


async def test_quality_gate_rejection_never_blocks_the_farmer_and_is_kept_for_operations(env, face):
    blur = {"error": "image quality check failed", "issues": ["selfie is too blurry (sharpness 18.4 < 60.0)"]}
    face.script = [httpx.Response(422, json=blur), httpx.Response(422, json=blur)]  # still too blurry after the retry
    await with_selfie(env)
    (selfie,) = await rows(env, "SELFIE")
    assert selfie.face_check_status == "ERROR" and "too blurry" in selfie.face_error_message
    assert await env.stage() == "COLLECT_FARM_PHOTOS" and (await draft(env))["selfie_doc"] == str(selfie.id)
    assert "blurry" not in " ".join(env.graph.texts()) and "sharpness" not in " ".join(env.graph.texts())


async def test_error_message_from_the_api_is_kept_for_operations_only(env, face):
    face.script = [reply(error="no face detected in id_image")]
    await with_selfie(env)
    (selfie,) = await rows(env, "SELFIE")
    assert selfie.face_error_message == "no face detected in id_image"
    assert "no face detected" not in " ".join(env.graph.texts())


async def test_disabled_makes_no_api_call(env, face):
    env.c.settings.face_verify_enabled = False
    await with_selfie(env)
    assert face.requests == [] and "Checking your selfie" not in " ".join(env.graph.texts())
    (selfie,) = await rows(env, "SELFIE")
    assert selfie.face_check_status == "SKIPPED" and await env.stage() == "COLLECT_FARM_PHOTOS"


async def test_the_check_never_verifies_a_farmer(env, face):
    face.verdict(verified=True)
    await with_selfie(env)
    await env.button("farmphoto_skip")
    await env.button("cropphoto_skip")
    await env.button("review_confirm", "Confirm")
    f = await env.farmer()
    assert f.selfie_status == "RECEIVED" and f.verification_status == "PENDING" and f.verification_status != "VERIFIED"


# ------------------------------------------------------------------ 5. flow: PDF ID
async def test_pdf_id_front_is_converted_to_a_png_before_sending(env, face):
    await env.run_registration_until("id_type")
    await env.document(mime="application/pdf", data=real_pdf())
    assert await env.stage() == "COLLECT_SELFIE"
    await env.identity_image()
    (req,) = face.requests
    assert b'name="id_image"; filename="id.png"' in req.content and b"\x89PNG" in req.content
    assert b"%PDF" not in req.content
    (id_front,) = await rows(env, "ID_FRONT")
    assert id_front.mime_type == "application/pdf"  # what is stored is untouched


async def test_a_pdf_that_cannot_be_converted_skips_the_check(env, face):
    await env.run_registration_until("id_type")
    await env.document(mime="application/pdf")  # the test PDF is not a renderable document
    await env.identity_image()
    assert face.requests == []
    (selfie,) = await rows(env, "SELFIE")
    assert selfie.face_check_status == "SKIPPED" and selfie.face_error_message == "pdf_conversion_failed"
    assert await env.stage() == "COLLECT_FARM_PHOTOS"


# ------------------------------------------------------------------ 6. flow: no ID yet, then the ID arrives
async def test_no_accepted_id_yet_is_pending_id_and_runs_when_the_id_is_accepted(env, face):
    face.verdict(verified=True)
    await env.run_registration_until("location")
    await env.button("id_later", "Send later")
    await env.identity_image()  # the selfie, with no ID on file
    assert face.requests == [] and "Checking your selfie" not in " ".join(env.graph.texts())
    (selfie,) = await rows(env, "SELFIE")
    assert selfie.face_check_status == "PENDING_ID" and selfie.face_compared_id_document_id is None
    assert await env.stage() == "COLLECT_FARM_PHOTOS" and "selfie has been received" in env.graph.texts()[-1]
    await env.button("farmphoto_skip")
    await env.button("cropphoto_skip")
    await env.button("review_confirm", "Confirm")
    f = await env.farmer()
    assert f.selfie_status == "RECEIVED" and f.id_document_status == "DEFERRED" and f.verification_status == "NOT_SUBMITTED"

    await env.button("identity_start", "Send now")  # later: the farmer sends the ID
    await env.button("idtype_PASSPORT", "Passport")
    await env.identity_image()
    assert len(face.requests) == 1  # ran automatically once the ID was accepted
    (selfie,) = await rows(env, "SELFIE")
    (id_front,) = await rows(env, "ID_FRONT")
    assert selfie.face_check_status == "MATCHED" and selfie.face_compared_id_document_id == id_front.id
    f = await env.farmer()
    assert (f.id_document_status, f.selfie_status, f.verification_status) == ("RECEIVED", "RECEIVED", "PENDING")


async def test_a_mismatch_when_the_id_arrives_later_asks_the_farmer_to_choose(env, face):
    await env.run_registration_until("location")
    await env.button("idtype_none", "I don't have any")  # NEEDS_HELP
    await env.identity_image()
    await env.button("farmphoto_skip")
    await env.button("cropphoto_skip")
    await env.button("review_confirm", "Confirm")
    await env.button("identity_start", "Send now")
    await env.button("idtype_PASSPORT", "Passport")
    await env.identity_image()  # the face check runs against the selfie from registration: mismatch
    assert env.graph.last_buttons() == ["selfie_new", "id_reupload"] and await env.stage() == "COLLECT_SELFIE"
    await env.button("selfie_new", "Take a new selfie")
    face.verdict(verified=True)
    await env.identity_image()
    f = await env.farmer()
    assert (f.id_document_status, f.selfie_status, f.verification_status) == ("RECEIVED", "RECEIVED", "PENDING")


# ------------------------------------------------------------------ 7. flow: the farmer's choices
async def test_take_a_new_selfie_supersedes_the_old_one_with_a_new_challenge_and_tips(env, face):
    await with_selfie(env)
    before = (await draft(env))["selfie_challenge"]
    await env.button("selfie_new", "Take a new selfie")
    assert "Tips for the new selfie" in env.graph.texts()[-1] and "finger" in env.graph.texts()[-1]
    (old,) = await rows(env, "SELFIE")
    assert old.status == "SUPERSEDED"
    dr = await draft(env)
    assert dr["selfie_challenge"] != before and not dr["face_choice_pending"] and await env.stage() == "COLLECT_SELFIE"
    face.verdict(verified=True)
    await env.identity_image()
    assert await env.stage() == "COLLECT_FARM_PHOTOS" and len(face.requests) == 2


async def test_upload_another_id_supersedes_the_id_and_the_new_one_is_compared_with_the_current_selfie(env, face):
    await with_selfie(env)
    (first_id,) = await rows(env, "ID_FRONT")
    (selfie,) = await rows(env, "SELFIE")
    await env.button("id_reupload", "Upload another ID")
    assert env.graph.last()["interactive"]["action"].get("sections")  # back to the ID type list
    assert (await rows(env, "ID_FRONT"))[0].status == "SUPERSEDED" and first_id.id == (await rows(env, "ID_FRONT"))[0].id
    assert (await draft(env))["selfie_doc"] == str(selfie.id)  # the selfie stays
    face.verdict(verified=True)
    await env.button("idtype_OMANG", "Omang")
    await env.identity_image()
    assert len(face.requests) == 2
    new_id = (await rows(env, "ID_FRONT"))[-1]
    assert new_id.id != first_id.id and new_id.status == "ACCEPTED"
    (selfie,) = await rows(env, "SELFIE")
    assert selfie.face_check_status == "MATCHED" and selfie.face_compared_id_document_id == new_id.id
    assert selfie.face_check_attempts == 1 and await env.stage() == "COLLECT_FARM_PHOTOS"
    assert face.requests[0].content != face.requests[1].content  # a different ID went out the second time


async def test_the_new_id_goes_through_the_name_check_before_the_face_check(env, face):
    name_calls: list[httpx.Request] = []

    def name_api(request: httpx.Request) -> httpx.Response:
        name_calls.append(request)
        return httpx.Response(200, json={"fields": {"given_names": {"value": "John"}}})

    s = env.c.settings
    s.doc_extract_enabled, s.doc_extract_api_url, s.doc_extract_retry_base_delay = True, "https://extract.test/x", 0
    env.c.doc_extract = DocExtractService(s, client=httpx.AsyncClient(transport=httpx.MockTransport(name_api)))
    await with_selfie(env)  # the Omang is not name-checked; the face check mismatches
    assert name_calls == [] and env.graph.last_buttons() == ["selfie_new", "id_reupload"]
    await env.button("id_reupload", "Upload another ID")
    face.verdict(verified=True)
    await env.button("idtype_PASSPORT", "Passport")
    await env.identity_image()
    assert len(name_calls) == 1  # name check first (a passport)
    assert len(face.requests) == 2 and await env.stage() == "COLLECT_FARM_PHOTOS"
    (selfie,) = await rows(env, "SELFIE")
    assert selfie.face_check_status == "MATCHED"


async def test_free_text_phrases_are_routed_without_claude(env, face):
    await with_selfie(env)
    calls = len(env.claude.contexts)
    await env.text("take a new selfie")
    assert not (await draft(env))["face_choice_pending"] and (await rows(env, "SELFIE"))[0].status == "SUPERSEDED"
    assert len(env.claude.contexts) == calls


async def test_free_text_is_interpreted_by_claude(env, face):
    await with_selfie(env)
    env.claude.push(make_ai(Intent.SUBMIT_IDENTITY_DOCUMENTS, identity_choice="NEW_SELFIE"))
    await env.text("I'll send another selfie")
    assert (await rows(env, "SELFIE"))[0].status == "SUPERSEDED" and await env.stage() == "COLLECT_SELFIE"
    face.verdict()  # mismatch again
    await env.identity_image()
    env.claude.push(make_ai(Intent.SUBMIT_IDENTITY_DOCUMENTS, identity_choice="OTHER_ID"))
    await env.text("can I use my voter ID")
    assert (await rows(env, "ID_FRONT"))[0].status == "SUPERSEDED" and await env.stage() == "COLLECT_ID_DOCUMENT"


async def test_other_free_text_shows_the_two_buttons_again(env, face):
    await with_selfie(env)
    env.claude.push(make_ai(Intent.GREETING))
    await env.text("hello?")
    assert env.graph.last_buttons() == ["selfie_new", "id_reupload"] and (await draft(env))["face_choice_pending"]


async def test_stop_is_still_honoured_while_the_choice_is_open(env, face):
    await with_selfie(env)
    env.claude.push(make_ai(Intent.CANCEL_REGISTRATION))
    await env.text("cancel registration")
    assert "stop your registration" in env.graph.texts()[-1].lower()


async def test_photo_or_other_buttons_while_the_choice_is_open_show_the_choice_again(env, face):
    await with_selfie(env)
    await env.identity_image()
    assert env.graph.last_buttons() == ["selfie_new", "id_reupload"] and len(face.requests) == 1
    await env.button("selfie_later", "Send later")
    assert env.graph.last_buttons() == ["selfie_new", "id_reupload"] and not (await draft(env))["selfie_deferred"]


async def test_stale_choice_buttons_are_ignored_when_nothing_is_pending(env, face):
    face.verdict(verified=True)
    await with_selfie(env)
    await env.button("selfie_new")
    assert await env.stage() == "COLLECT_FARM_PHOTOS" and (await rows(env, "SELFIE"))[0].status == "ACCEPTED"


# ------------------------------------------------------------------ 8. attempt limit
async def test_after_the_maximum_attempts_the_team_reviews_and_the_flow_continues(env, face):
    await with_selfie(env)  # failed check 1
    await env.button("selfie_new")
    await env.identity_image()  # failed check 2
    await env.button("selfie_new")
    await env.identity_image()  # failed check 3: stop asking
    assert "Ezina team will review your photos" in env.graph.texts()[-1]
    dr = await draft(env)
    assert dr["selfie_needs_help"] and dr["selfie_doc"] is None and not dr["face_choice_pending"]
    assert await env.stage() == "COLLECT_FARM_PHOTOS"
    selfies = await rows(env, "SELFIE")
    assert [s.status for s in selfies] == ["SUPERSEDED", "SUPERSEDED", "ACCEPTED"]  # all kept for the review
    assert [s.face_check_attempts for s in selfies] == [1, 2, 3]
    await env.button("farmphoto_skip")
    await env.button("cropphoto_skip")
    await env.button("review_confirm", "Confirm")
    f = await env.farmer()
    assert f.selfie_status == "NEEDS_HELP" and f.verification_status == "NOT_SUBMITTED"


async def test_attempts_count_new_ids_as_well_as_new_selfies(env, face):
    await with_selfie(env)  # 1: mismatch
    await env.button("id_reupload")
    await env.button("idtype_OMANG")
    await env.identity_image()  # 2: mismatch with the new ID
    assert env.graph.last_buttons() == ["selfie_new", "id_reupload"]
    await env.button("selfie_new")
    await env.identity_image()  # 3: stop
    assert "Ezina team will review your photos" in env.graph.texts()[-1]
    assert (await draft(env))["selfie_needs_help"]


async def test_attempt_limit_is_configurable(env, face):
    env.c.settings.face_verify_max_attempts = 1
    await with_selfie(env)
    assert (await draft(env))["selfie_needs_help"] and await env.stage() == "COLLECT_FARM_PHOTOS"


async def test_the_running_total_survives_into_the_later_identity_flow(env, face):
    face.verdict(verified=True)
    await env.run_registration_until("location")
    await env.button("id_later", "Send later")
    await env.identity_image()
    await env.button("farmphoto_skip")
    await env.button("cropphoto_skip")
    await env.button("review_confirm", "Confirm")
    async with env.c.db.sessionmaker() as s, s.begin():  # two failed checks are already on the selfie's row
        (selfie,) = [d for d in await env.all(IdentityDocument) if d.kind == "SELFIE"]
        (await s.get(IdentityDocument, selfie.id)).face_check_attempts = 2
    face.verdict()  # mismatch
    await env.button("identity_start", "Send now")
    assert (await draft(env))["face_check_attempts"] == 2
    await env.button("idtype_PASSPORT")
    await env.identity_image()  # the third failure ends it
    assert "Ezina team will review your photos" in env.graph.texts()[-1]


# ------------------------------------------------------------------ 9. privacy, wording and Claude
async def test_scores_never_reach_logs_claude_prompts_or_farmer_messages(env, face, caplog):
    with caplog.at_level(logging.DEBUG, logger="ezina"):
        await with_selfie(env)
        env.claude.push(make_ai(Intent.GREETING))
        await env.text("hello?")
        await env.button("selfie_new")
        await env.identity_image()
    assert env.claude.contexts
    for ctx in env.claude.contexts:
        prompt = build_user_message(ctx)
        for secret in (SCORE, "0.68", "ArcFace", "retinaface", "no_match"):
            assert secret not in prompt
    for secret in (SCORE, "0.68", "no_match", "retinaface"):
        assert secret not in app_log_text(caplog)
        assert secret not in " ".join(env.graph.texts())
    assert "image/jpeg" not in app_log_text(caplog) or "IDBYTES" not in app_log_text(caplog)


async def test_non_english_mismatch_wording_comes_from_claude_and_is_guarded(env, face):
    await to_selfie(env)
    async with env.c.db.sessionmaker() as s, s.begin():
        conv = await s.get(Conversation, (await env.conv()).id)
        conv.draft = {**conv.draft, "preferred_language": "tn"}
    env.claude.push(make_ai(text="Selfie ya gago ga e tshwane le setshwantsho sa ID. Tlhopha tsela."))
    await env.identity_image()
    assert env.graph.texts()[-1].startswith("Selfie ya gago ga e tshwane") and env.graph.last_buttons() == ["selfie_new", "id_reupload"]
    ctx = env.claude.contexts[-1]
    assert ctx.mode == "compose" and "face_check" in ctx.saved_summary
    assert SCORE not in build_user_message(ctx)


async def test_unsafe_non_english_wording_falls_back_to_the_template(env, face):
    await to_selfie(env)
    async with env.c.db.sessionmaker() as s, s.begin():
        conv = await s.get(Conversation, (await env.conv()).id)
        conv.draft = {**conv.draft, "preferred_language": "tn"}
    env.claude.push(make_ai(text="Your ID is fake. Send your ID number 1234567890123 now."))
    await env.identity_image()
    assert env.graph.texts()[-1].startswith("Your selfie doesn't seem to match the photo on your ID")


def test_the_reply_guard_allows_a_face_match_statement_only_when_python_supplied_the_result():
    text = "Your selfie does not seem to match the photo on your ID."
    assert reply_guard.check_reply(text, Draft()) == (False, "judges_identity_document")
    assert reply_guard.check_reply(text, Draft(), face_result_supplied=True) == (True, "ok")
    # calling an ID fake stays forbidden even then
    assert reply_guard.check_reply("Your ID is fake.", Draft(), face_result_supplied=True)[0] is False
    assert reply_guard.check_reply("The ID card looks fake.", Draft(), face_result_supplied=True)[0] is False


async def test_admin_detail_returns_the_face_result_on_the_selfie_row_only(env, face):
    await with_selfie(env)
    f = await env.farmer()
    r = await env.client.get(f"/api/admin/farmers/{f.id}", headers={"X-API-Key": ADMIN_KEY})
    ident = r.json()["identity_documents"]
    (selfie,) = [d for d in ident if d["kind"] == "SELFIE"]
    (id_front,) = [d for d in ident if d["kind"] == "ID_FRONT"]
    assert selfie["face_check_status"] == "MISMATCH" and selfie["face_distance"] == 0.9673 and selfie["face_threshold"] == 0.68
    assert selfie["face_compared_id_document_id"] == id_front["id"] and selfie["face_check_attempts"] == 1
    assert id_front["face_check_status"] is None and id_front["face_distance"] is None


# ------------------------------------------------------------------ 10. migration 0005
def _alembic(db, *args):
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


NEW_COLS = {
    "face_check_status", "face_compared_id_document_id", "face_verified", "face_distance", "face_threshold",
    "face_confidence_band", "face_liveness_passed", "face_found_id", "face_found_selfie", "face_model", "face_detector",
    "face_processing_ms", "face_warnings", "face_error_message", "face_check_attempts", "face_checked_at",
}


def test_migration_0005_adds_the_face_columns_and_is_reversible(tmp_path):
    import sqlite3

    db = tmp_path / "old.db"
    with sqlite3.connect(db) as c:  # identity_documents as it was before the face check
        c.execute("create table identity_documents (id CHAR(32) primary key, farmer_id CHAR(32), kind varchar(10), "
                  "status varchar(12), created_at datetime, updated_at datetime)")
        c.execute("insert into identity_documents (id, kind, status) values ('a', 'ID_FRONT', 'ACCEPTED')")
        c.execute("insert into identity_documents (id, kind, status) values ('b', 'SELFIE', 'ACCEPTED')")
    assert _alembic(db, "stamp", "0004").returncode == 0
    r = _alembic(db, "upgrade", "head")
    assert r.returncode == 0, r.stderr
    assert NEW_COLS <= _ident_cols(db)
    with sqlite3.connect(db) as c:
        assert c.execute("select kind, face_check_status, face_check_attempts from identity_documents order by id").fetchall() == [
            ("ID_FRONT", None, 0), ("SELFIE", None, 0)]
        c.execute("update identity_documents set face_check_status = 'MATCHED' where id = 'b'")  # a selfie may carry it
        with pytest.raises(sqlite3.IntegrityError):  # any other kind may not
            c.execute("update identity_documents set face_check_status = 'MATCHED' where id = 'a'")
        with pytest.raises(sqlite3.IntegrityError):
            c.execute("update identity_documents set face_distance = 0.5 where id = 'a'")
        with pytest.raises(sqlite3.IntegrityError):  # and the status must be one of the enum values
            c.execute("update identity_documents set face_check_status = 'BOGUS' where id = 'b'")
    assert _alembic(db, "downgrade", "0004").returncode == 0
    assert not NEW_COLS & _ident_cols(db)


def test_migration_0005_on_a_fresh_database_is_a_no_op_after_0001(tmp_path):
    db = tmp_path / "fresh.db"
    assert _alembic(db, "upgrade", "head").returncode == 0
    assert NEW_COLS <= _ident_cols(db)
    assert _alembic(db, "upgrade", "head").returncode == 0
    assert _alembic(db, "downgrade", "0004").returncode == 0
    assert not NEW_COLS & _ident_cols(db)
