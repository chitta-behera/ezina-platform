"""Selfie face check: the ezina_id_verify integration, how Python reads its result, and the farmer-facing flow.

ezina_id_verify.match_face is mocked (AWS is never called). The scores are for the operations team only: these tests
also prove they never reach a farmer message, a log line or a Claude prompt, and that the check never verifies a farmer.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os

import pytest
from ezina_id_verify import FaceMatchResult, RekognitionServiceError, UnsupportedFile
from PIL import Image

from app.config import Settings
from app.enums import FaceCheckStatus, Intent
from app.models import Conversation, IdentityDocument
from app.schemas.conversation import Draft
from app.services import doc_extract_service, face_verify_service
from app.services.claude_service import build_user_message
from app.services.doc_extract_service import DocExtractService
from app.services.face_verify_service import FaceResult, FaceVerifyError, FaceVerifyService, classify
from app.workflows import messages as M
from app.workflows import reply_guard
from tests.conftest import ADMIN_KEY, make_ai, make_image

SCORE = "41.3"  # the similarity in the default (mismatch) result: must never reach the farmer


def result(**over) -> FaceMatchResult:
    """A FaceMatchResult as ezina_id_verify returns it: a mismatch by default."""
    base = dict(
        verified=False, similarity=41.3, threshold=90.0, confidence_band="no_match", face_found_id=True,
        face_found_selfie=True, liveness_passed=None, selfie_quality_ok=True, model="aws-rekognition-compare-faces",
        processing_ms=5200.5, error=None, warnings=[],
    )
    return FaceMatchResult(**{**base, **over})


class FaceMock:
    """Stands in for ezina_id_verify.match_face: records the calls, answers from a script, never touches AWS."""

    def __init__(self):
        self.requests: list[tuple[bytes, bytes]] = []  # (id_image, selfie_image) per call
        self.script: list = []  # FaceMatchResult | Exception, popped first
        self.default = result()
        self.delay = 0.0

    async def __call__(self, id_image: bytes, selfie_image: bytes) -> FaceMatchResult:
        self.requests.append((id_image, selfie_image))
        if self.delay:
            await asyncio.sleep(self.delay)
        item = self.script.pop(0) if self.script else self.default
        if isinstance(item, Exception):
            raise item
        return item

    def verdict(self, **over) -> None:
        self.default = result(**over)


@pytest.fixture
def make_service(monkeypatch):
    def factory(**overrides) -> tuple[FaceVerifyService, FaceMock]:
        mock = FaceMock()
        monkeypatch.setattr(face_verify_service, "match_face", mock)
        return FaceVerifyService(Settings(**{"_env_file": None, "face_verify_enabled": True, **overrides})), mock

    return factory


async def call(svc: FaceVerifyService, **kw) -> FaceResult:
    args = dict(id_image=b"IDBYTES", id_mime="image/png", selfie_image=b"SELFIEBYTES", selfie_mime="image/jpeg")
    return await svc.verify(**{**args, **kw})


@pytest.fixture
def face(env, monkeypatch):
    """The running app with the face check switched on and match_face mocked (a mismatch by default)."""
    mock = FaceMock()
    monkeypatch.setattr(face_verify_service, "match_face", mock)
    s = env.c.settings
    s.face_verify_enabled = True
    env.c.face_verify = FaceVerifyService(s)
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


# ------------------------------------------------------------------ 1. the service calls ezina_id_verify
async def test_match_face_gets_the_id_image_then_the_selfie_as_raw_bytes_and_nothing_else(make_service):
    svc, mock = make_service()
    await call(svc)
    assert mock.requests == [(b"IDBYTES", b"SELFIEBYTES")]  # no content types: the package detects JPEG/PNG itself


async def test_the_sample_result_is_kept_field_by_field(make_service):
    svc, mock = make_service()
    mock.default = result(verified=True, similarity=97.25, confidence_band="match", warnings=["eyes_closed"], processing_ms=7300.0)
    r = await call(svc)
    assert (r.verified, r.similarity, r.threshold, r.confidence_band) == (True, 97.25, 90.0, "match")
    assert (r.liveness_passed, r.face_found_id, r.face_found_selfie, r.selfie_quality_ok) == (None, True, True, True)
    assert (r.model, r.processing_ms, r.error, r.warnings) == ("aws-rekognition-compare-faces", 7300.0, None, ["eyes_closed"])
    assert (r.distance, r.detector) == (None, None)  # the old API's fields are never set
    assert classify(r) == FaceCheckStatus.MATCHED


@pytest.mark.parametrize("failure,reason", [
    (RekognitionServiceError("AWS failed", "ThrottlingException"), "ThrottlingException"),
    (UnsupportedFile("not a JPEG/PNG"), "UnsupportedFile"),
    (RuntimeError("anything else"), "RuntimeError"),
])
async def test_package_exceptions_become_one_service_error_without_a_retry(make_service, failure, reason):
    svc, mock = make_service()
    mock.script = [failure, failure, failure]
    with pytest.raises(FaceVerifyError) as e:
        await call(svc)
    assert e.value.reason == reason
    assert len(mock.requests) == 1  # ezina_id_verify already retries AWS errors: nothing is retried here


async def test_the_service_logs_timing_but_never_scores_images_or_warnings_text(make_service, caplog):
    svc, mock = make_service()
    mock.default = result(warnings=["eyes_closed"])
    with caplog.at_level(logging.DEBUG, logger="ezina"):
        await call(svc)
    assert "face verify call" in caplog.text
    text = app_log_text(caplog)
    for secret in (SCORE, "IDBYTES", "SELFIEBYTES", "eyes_closed", "no_match"):
        assert secret not in text


def test_availability_follows_the_switch_only(make_service):
    svc, _ = make_service()
    assert svc.available
    assert not FaceVerifyService(Settings(_env_file=None, face_verify_enabled=False)).available


def test_no_http_integration_remains():
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent / "app"
    for path in (root / "services" / "face_verify_service.py", root / "services" / "doc_extract_service.py", root / "config.py"):
        text = path.read_text(encoding="utf-8")
        for gone in ("httpx", "FACE_VERIFY_API_URL", "face_verify_api_url", "DOC_EXTRACT_API_URL", "doc_extract_api_url",
                     "face_verify_api_key", "doc_extract_api_key", "face_verify_max_retries", "doc_extract_max_retries"):
            assert gone not in text, (path.name, gone)
    for name in ("face_verify_api_url", "doc_extract_api_url", "face_verify_timeout_seconds", "doc_extract_timeout_seconds"):
        assert name not in Settings.model_fields


# ------------------------------------------------------------------ 2. how Python reads the result
@pytest.mark.parametrize("over,expected", [
    ({"verified": True, "confidence_band": "match"}, FaceCheckStatus.MATCHED),
    ({"verified": False, "confidence_band": "no_match"}, FaceCheckStatus.MISMATCH),
    ({"verified": False, "confidence_band": "possible_match", "similarity": 82.0}, FaceCheckStatus.MISMATCH),
    ({"face_found_id": False}, FaceCheckStatus.NO_FACE_ID),
    ({"face_found_selfie": False}, FaceCheckStatus.NO_FACE_SELFIE),
    # the order: error, no face in the ID, no face in the selfie, verified / not verified
    ({"error": "selfie_image_rejected"}, FaceCheckStatus.ERROR),
    ({"error": "x", "verified": True}, FaceCheckStatus.ERROR),
    ({"error": "x", "face_found_id": False}, FaceCheckStatus.ERROR),  # an error wins over a no-face flag
    ({"face_found_id": False, "face_found_selfie": False}, FaceCheckStatus.NO_FACE_ID),
    ({"face_found_selfie": False, "verified": True}, FaceCheckStatus.NO_FACE_SELFIE),
    # liveness is never reported by Rekognition (None) and is never consulted: it cannot produce LIVENESS_FAILED
    ({"liveness_passed": None, "verified": False}, FaceCheckStatus.MISMATCH),
    ({"liveness_passed": False, "verified": True}, FaceCheckStatus.MATCHED),
    ({"liveness_passed": False, "verified": False}, FaceCheckStatus.MISMATCH),
    # selfie quality warnings never override a MATCHED result
    ({"verified": True, "warnings": ["eyes_closed", "selfie_blurry", "selfie_dark", "sunglasses", "multiple_faces_selfie"],
      "selfie_quality_ok": False}, FaceCheckStatus.MATCHED),
])
async def test_classify_follows_the_documented_order(make_service, over, expected):
    svc, mock = make_service()
    mock.default = result(**over)
    status = classify(await call(svc))
    assert status == expected
    assert status != FaceCheckStatus.LIVENESS_FAILED


def test_a_result_with_no_verdict_is_an_error():
    assert classify(FaceResult()) == FaceCheckStatus.ERROR
    assert classify(FaceResult(model="aws-rekognition-compare-faces")) == FaceCheckStatus.ERROR


# ------------------------------------------------------------------ 3. the retry tip comes from the selfie warnings
@pytest.mark.parametrize("warnings,tip", [
    (["eyes_closed"], "Keep your eyes open"), (["sunglasses"], "take off your sunglasses"), (["selfie_dark"], "Face the light"),
    (["selfie_blurry"], "steady"), (["multiple_faces_selfie"], "only your face"),
    (["selfie_dark", "eyes_closed"], "Keep your eyes open"),  # one tip: the first in priority order
])
def test_one_specific_tip_is_chosen_from_the_warnings(warnings, tip):
    assert tip in (M.face_tip(warnings) or "")


def test_no_tip_without_a_known_warning():
    assert M.face_tip([]) is None and M.face_tip(None) is None and M.face_tip(["small_face_id"]) is None
    assert "Keep your eyes open" not in M.face_mismatch_reply().body
    assert "Keep your eyes open" in M.face_mismatch_reply(M.face_tip(["eyes_closed"])).body


# ------------------------------------------------------------------ 4. flow: results
async def test_mismatch_offers_two_buttons_with_tips_and_shows_no_score(env, face):
    await with_selfie(env)
    texts = env.graph.texts()
    assert "Checking your selfie" in " ".join(texts)  # the API is slow: the holding message comes first
    msg = texts[-1]
    assert msg.startswith("Your selfie doesn't seem to match the photo on your ID. Please choose an option:")
    assert "face the light" in msg and "no cap or sunglasses" in msg
    assert env.graph.last_buttons() == ["selfie_new", "id_reupload"]
    for secret in (SCORE, "90.0", "aws-rekognition", "no_match"):
        assert secret not in " ".join(texts)
    (selfie,) = await rows(env, "SELFIE")
    (id_front,) = await rows(env, "ID_FRONT")
    assert selfie.face_check_status == "MISMATCH" and selfie.face_verified is False
    assert float(selfie.face_similarity) == 41.3 and float(selfie.face_threshold) == 90.0 and selfie.face_distance is None
    assert (selfie.face_confidence_band, selfie.face_model, selfie.face_detector) == (
        "no_match", "aws-rekognition-compare-faces", None)
    assert selfie.face_liveness_passed is None and selfie.face_found_id and selfie.face_found_selfie
    assert selfie.face_selfie_quality_ok is True
    assert float(selfie.face_processing_ms) == 5200.5 and selfie.face_warnings is None and selfie.face_error_message is None
    assert selfie.face_compared_id_document_id == id_front.id and selfie.face_check_attempts == 1
    assert selfie.face_checked_at is not None and selfie.status == "ACCEPTED"
    dr = await draft(env)
    assert dr["face_choice_pending"] and dr["selfie_doc"] is None and await env.stage() == "COLLECT_SELFIE"
    assert id_front.face_check_status is None  # the face check lives on the selfie row only


async def test_the_images_sent_are_the_stored_id_front_and_selfie_bytes(env, face):
    await to_selfie(env)
    (id_front,) = await rows(env, "ID_FRONT")
    await env.identity_image()
    (req,) = face.requests
    (selfie,) = await rows(env, "SELFIE")
    stored_id = await env.c.identity.storage.get(id_front.storage_key)
    stored_selfie = await env.c.identity.storage.get(selfie.storage_key)
    assert req == (stored_id, stored_selfie)  # the current ACCEPTED ID front, then the current selfie


async def test_matched_continues_and_marks_the_selfie_received(env, face):
    face.verdict(verified=True, similarity=96.0, confidence_band="match")
    await with_selfie(env)
    assert env.graph.texts()[-1].startswith("Thank you, your selfie has been received ✅.")
    assert await env.stage() == "COLLECT_FARM_PHOTOS"
    (selfie,) = await rows(env, "SELFIE")
    assert selfie.face_check_status == "MATCHED" and selfie.face_verified is True and selfie.face_check_attempts == 0
    assert (await draft(env))["selfie_doc"] == str(selfie.id)
    assert "96.0" not in " ".join(env.graph.texts())


async def test_no_face_in_the_id_asks_for_a_clearer_id_photo_and_supersedes_the_id(env, face):
    face.verdict(face_found_id=False, verified=False)
    await with_selfie(env)
    assert "photo on your ID isn't clear" in env.graph.texts()[-1]
    assert await rows(env, "ID_FRONT") == []  # the unclear ID is deleted
    (selfie,) = await rows(env, "SELFIE")
    assert selfie.face_check_status == "NO_FACE_ID" and selfie.status == "ACCEPTED"
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





async def test_no_face_in_the_selfie_asks_for_a_new_one_with_a_new_challenge(env, face):
    face.verdict(face_found_selfie=False)
    await to_selfie(env)
    old = (await draft(env))["selfie_challenge"]
    await env.identity_image()
    msg = env.graph.texts()[-1]
    assert "take a new selfie now with your front camera" in msg and "finger" in msg
    assert "selfie_new" not in env.graph.last_buttons()  # no choice to make: just a new selfie
    (selfie,) = await rows(env, "SELFIE")
    assert selfie.face_check_status == "NO_FACE_SELFIE" and selfie.status == "REJECTED"
    dr = await draft(env)
    assert dr["selfie_doc"] is None and dr["selfie_challenge"] != old and await env.stage() == "COLLECT_SELFIE"
    face.verdict(verified=True)
    await env.identity_image()
    assert await env.stage() == "COLLECT_FARM_PHOTOS"


async def test_a_rejected_photo_never_blocks_the_farmer_and_the_reason_is_kept_for_operations(env, face):
    face.script = [result(error="selfie_image_rejected", face_found_selfie=False, verified=False)]
    await with_selfie(env)
    (selfie,) = await rows(env, "SELFIE")
    assert selfie.face_check_status == "ERROR" and selfie.face_error_message == "selfie_image_rejected"
    assert await env.stage() == "COLLECT_FARM_PHOTOS" and (await draft(env))["selfie_doc"] == str(selfie.id)
    assert "rejected" not in " ".join(env.graph.texts())


async def test_error_message_from_the_api_is_kept_for_operations_only(env, face):
    face.script = [result(error="no face detected in id_image")]
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
async def test_a_pdf_id_front_stored_earlier_is_converted_to_a_png_before_matching(env, face):
    # PDFs are refused now; an ID stored as a PDF before that is still converted (enable PDFs to create one here)
    env.c.settings.identity_document_mime = ("image/jpeg", "image/png", "application/pdf")
    await env.run_registration_until("id_type")
    await env.document(mime="application/pdf", data=real_pdf())
    assert await env.stage() == "COLLECT_SELFIE"
    await env.identity_image()
    (req,) = face.requests
    assert req[0].startswith(b"\x89PNG") and b"%PDF" not in req[0]
    (id_front,) = await rows(env, "ID_FRONT")
    assert id_front.mime_type == "application/pdf"  # what is stored is untouched


async def test_a_pdf_that_cannot_be_converted_skips_the_check(env, face):
    env.c.settings.identity_document_mime = ("image/jpeg", "image/png", "application/pdf")
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
    assert await rows(env, "ID_FRONT") == []  # the old ID is deleted
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
    assert face.requests[0][0] != face.requests[1][0]  # a different ID went out the second time


async def test_the_new_id_goes_through_the_name_check_before_the_face_check(env, face, monkeypatch):
    from ezina_id_verify import NameResult

    name_calls: list[tuple[str, bytes]] = []

    async def fake_extract_name(doc_type: str, image: bytes) -> NameResult:
        name_calls.append((doc_type, image))
        return NameResult(doc_type=doc_type, found=True, full_name="John", method="label", confidence=0.85, warnings=[])

    monkeypatch.setattr(doc_extract_service, "extract_name", fake_extract_name)
    s = env.c.settings
    s.doc_extract_enabled = True
    env.c.doc_extract = DocExtractService(s)
    await with_selfie(env)  # the Omang is name-checked too (botswana_omang); the face check mismatches
    assert [c[0] for c in name_calls] == ["botswana_omang"] and env.graph.last_buttons() == ["selfie_new", "id_reupload"]
    await env.button("id_reupload", "Upload another ID")
    face.verdict(verified=True)
    await env.button("idtype_PASSPORT", "Passport")
    await env.identity_image()
    assert [c[0] for c in name_calls] == ["botswana_omang", "passport"]  # name check first (a passport)
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
    assert await rows(env, "ID_FRONT") == [] and await env.stage() == "COLLECT_ID_DOCUMENT"


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
        for secret in (SCORE, "90.0", "aws-rekognition", "no_match"):
            assert secret not in prompt
    for secret in (SCORE, "90.0", "no_match", "aws-rekognition"):
        assert secret not in app_log_text(caplog)
        assert secret not in " ".join(env.graph.texts())


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
    face.verdict(similarity=82.4, confidence_band="possible_match", warnings=["eyes_closed"], selfie_quality_ok=False)
    await with_selfie(env)
    f = await env.farmer()
    r = await env.client.get(f"/api/admin/farmers/{f.id}", headers={"X-API-Key": ADMIN_KEY})
    ident = r.json()["identity_documents"]
    (selfie,) = [d for d in ident if d["kind"] == "SELFIE"]
    (id_front,) = [d for d in ident if d["kind"] == "ID_FRONT"]
    assert selfie["face_check_status"] == "MISMATCH" and selfie["face_similarity"] == 82.4 and selfie["face_threshold"] == 90.0
    assert selfie["face_confidence_band"] == "possible_match" and selfie["face_selfie_quality_ok"] is False
    assert selfie["face_warnings"] == ["eyes_closed"] and "face_distance" not in selfie
    assert selfie["face_compared_id_document_id"] == id_front["id"] and selfie["face_check_attempts"] == 1
    assert id_front["face_check_status"] is None and id_front["face_similarity"] is None


# ------------------------------------------------------------------ 10. new behaviour of the Rekognition integration
async def test_a_matched_result_stores_everything_and_warnings_do_not_override_it(env, face):
    face.verdict(verified=True, similarity=97.25, confidence_band="match", warnings=["eyes_closed"], selfie_quality_ok=False)
    await with_selfie(env)
    assert await env.stage() == "COLLECT_FARM_PHOTOS" and env.graph.texts()[-1].startswith("Thank you, your selfie has been received")
    assert "eyes" not in env.graph.texts()[-1].lower()  # a match is never second-guessed to the farmer
    (selfie,) = await rows(env, "SELFIE")
    assert selfie.face_check_status == "MATCHED" and selfie.face_verified is True
    assert float(selfie.face_similarity) == 97.25 and float(selfie.face_threshold) == 90.0
    assert selfie.face_confidence_band == "match" and selfie.face_liveness_passed is None
    assert selfie.face_found_id is True and selfie.face_found_selfie is True and selfie.face_selfie_quality_ok is False
    assert selfie.face_model == "aws-rekognition-compare-faces" and float(selfie.face_processing_ms) == 5200.5
    assert selfie.face_warnings == ["eyes_closed"] and selfie.face_error_message is None
    assert selfie.face_distance is None and selfie.face_detector is None  # the old API's columns are not written


@pytest.mark.parametrize("band,similarity", [("possible_match", 82.0), ("no_match", 12.0)])
async def test_possible_match_and_no_match_are_both_a_mismatch_with_the_two_buttons(env, face, band, similarity):
    face.verdict(verified=False, confidence_band=band, similarity=similarity)
    await with_selfie(env)
    assert env.graph.last_buttons() == ["selfie_new", "id_reupload"]
    (selfie,) = await rows(env, "SELFIE")
    assert selfie.face_check_status == "MISMATCH" and selfie.face_confidence_band == band
    assert str(similarity) not in " ".join(env.graph.texts()) and band not in " ".join(env.graph.texts())


async def test_liveness_none_never_produces_liveness_failed(env, face):
    face.verdict(verified=False, liveness_passed=None)
    await with_selfie(env)
    (selfie,) = await rows(env, "SELFIE")
    assert selfie.face_check_status == "MISMATCH" and selfie.face_liveness_passed is None


@pytest.mark.parametrize("warning,tip", [("eyes_closed", "Keep your eyes open"), ("sunglasses", "take off your sunglasses"),
                                         ("selfie_dark", "Face the light so your face"), ("selfie_blurry", "Hold the phone steady")])
async def test_a_mismatch_adds_one_specific_tip_from_the_selfie_warning(env, face, warning, tip):
    face.verdict(verified=False, warnings=[warning], selfie_quality_ok=False)
    await with_selfie(env)
    msg = env.graph.texts()[-1]
    assert msg.startswith("Your selfie doesn't seem to match the photo on your ID") and tip in msg
    assert env.graph.last_buttons() == ["selfie_new", "id_reupload"]


async def test_a_mismatch_without_a_warning_has_no_extra_tip(env, face):
    await with_selfie(env)
    assert "Keep your eyes open" not in env.graph.texts()[-1] and "sunglasses" not in env.graph.texts()[-1].replace("no cap or sunglasses", "")


async def test_no_face_in_the_selfie_adds_the_tip_too(env, face):
    face.verdict(face_found_selfie=False, warnings=["sunglasses"])
    await with_selfie(env)
    msg = env.graph.texts()[-1]
    assert "take a new selfie now with your front camera" in msg and "take off your sunglasses" in msg


async def test_the_tip_is_passed_to_claude_for_non_english_wording_without_scores(env, face):
    await to_selfie(env)
    async with env.c.db.sessionmaker() as s, s.begin():
        conv = await s.get(Conversation, (await env.conv()).id)
        conv.draft = {**conv.draft, "preferred_language": "tn"}
    face.verdict(verified=False, warnings=["eyes_closed"])
    env.claude.push(make_ai(text="Selfie ya gago ga e tshwane le setshwantsho sa ID. Bula matlho. Tlhopha tsela."))
    await env.identity_image()
    ctx = env.claude.contexts[-1]
    assert "Keep your eyes open" in (ctx.reply_target or "") and SCORE not in build_user_message(ctx)


async def test_the_selfie_quality_fields_survive_a_later_check(env, face):
    face.verdict(verified=False, warnings=["selfie_dark"], selfie_quality_ok=False)
    await with_selfie(env)
    await env.button("selfie_new")
    face.verdict(verified=True)
    await env.identity_image()
    first, second = await rows(env, "SELFIE")
    assert first.face_warnings == ["selfie_dark"] and first.face_selfie_quality_ok is False
    assert second.face_warnings is None and second.face_check_status == "MATCHED"


async def test_the_database_rejects_face_columns_on_id_rows(env, face):
    from sqlalchemy.exc import IntegrityError

    await with_selfie(env)
    (id_front,) = await rows(env, "ID_FRONT")
    for column, value in (("face_similarity", 90.0), ("face_selfie_quality_ok", True), ("face_threshold", 90.0),
                          ("face_check_status", "MATCHED")):
        with pytest.raises(IntegrityError):
            async with env.c.db.sessionmaker() as s, s.begin():
                setattr(await s.get(IdentityDocument, id_front.id), column, value)
    async with env.c.db.sessionmaker() as s, s.begin():  # the same columns are fine on the selfie
        (selfie,) = [d for d in await env.all(IdentityDocument) if d.kind == "SELFIE"]
        row = await s.get(IdentityDocument, selfie.id)
        row.face_similarity, row.face_selfie_quality_ok = 91.0, True


async def test_the_flag_for_operations_log_has_no_personal_data(env, face, caplog):
    face.script = [RekognitionServiceError("AWS failed for SECRET-NAME-IN-MESSAGE", "ThrottlingException")]
    with caplog.at_level(logging.DEBUG, logger="ezina"):
        await with_selfie(env)
    assert "SECRET-NAME-IN-MESSAGE" not in app_log_text(caplog)  # only the AWS error code is kept
    (selfie,) = await rows(env, "SELFIE")
    assert selfie.face_error_message == "ThrottlingException"


# ------------------------------------------------------------------ 11. migration 0005
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


# ------------------------------------------------------------------ a selfie with a problem can be sent again
async def test_the_same_selfie_can_be_sent_again_after_a_mismatch_and_a_new_selfie_request(env, face):
    photo = make_image()  # identical bytes both times (the helper makes a new random image otherwise)
    face.verdict(verified=False)
    await to_selfie(env)
    await env.identity_image(data=photo)
    assert "doesn't seem to match" in env.graph.texts()[-1] or "match" in env.graph.texts()[-1]
    await env.button("selfie_new", "Take a new selfie")
    face.verdict(verified=True)
    await env.identity_image(data=photo)
    assert "already been used" not in " ".join(env.graph.texts())
    assert await env.stage() == "COLLECT_FARM_PHOTOS"
    statuses = sorted(s.status for s in await rows(env, "SELFIE"))
    assert statuses == ["ACCEPTED", "SUPERSEDED"]  # the old row stays (it carries the attempt count)


async def test_the_same_selfie_can_be_sent_again_after_no_face_was_found(env, face):
    photo = make_image()
    face.verdict(face_found_selfie=False, verified=False)
    await to_selfie(env)
    await env.identity_image(data=photo)
    assert "new selfie" in env.graph.texts()[-1]
    face.verdict(verified=True)
    await env.identity_image(data=photo)
    assert "already been used" not in " ".join(env.graph.texts()) and await env.stage() == "COLLECT_FARM_PHOTOS"


async def test_another_farmers_selfie_photo_is_still_refused(env, face):
    import hashlib
    import uuid

    photo = make_image()
    await to_selfie(env)
    async with env.c.db.sessionmaker() as s, s.begin():
        s.add(IdentityDocument(
            farmer_id=uuid.uuid4(), country="BW", kind="SELFIE", wa_media_id="OTHERMEDIA", storage_key="identity/x/selfie/x.jpg",
            mime_type="image/jpeg", size_bytes=len(photo), sha256=hashlib.sha256(photo).hexdigest(), quality_result={},
            attempt=1, status="ACCEPTED", face_check_attempts=0))
    await env.identity_image(data=photo)
    assert "already been used" in env.graph.texts()[-1] and await env.stage() == "COLLECT_SELFIE"
