"""Identity verification: ID document + selfie (spec tests 21-30 and the submission rule)."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.database import utcnow
from app.enums import Intent
from app.models import Conversation, Farm, FarmDocument, Farmer, IdentityDocument, Message, Verification
from app.schemas.ai_response import Correction
from app.services.claude_service import build_user_message
from app.services.identity_service import IdentityRejected
from tests.conftest import E164, WA_ID, make_ai, make_image

ADMIN = {"X-API-Key": "test-admin-key"}


# ------------------------------------------------------------------ helpers
async def to_id_stage_india(env):
    """Registration up to the ID step for an Indian farmer (Claude scripted)."""
    ai = env.claude.push
    await env.run_registration_until("name")
    ai(make_ai(country="India", text="What is the full address of your farm?"))
    await env.text("India")
    ai(make_ai(full_address_text="Shirur village, Pune district, Maharashtra 412210", text="What crops do you grow at the moment?"))
    await env.text("Shirur village, Pune district, Maharashtra 412210")
    ai(make_ai(crops=["rice"], text="About how much land do you use for farming?"))
    await env.text("rice")
    ai(make_ai(cultivation_area=2, area_unit="acres", text="Share the location pin."))
    await env.text("2 acres")
    await env.location()
    assert await env.stage() == "COLLECT_ID_DOCUMENT"


async def draft(env) -> dict:
    return (await env.conv()).draft


async def identity_rows(env, *where):
    return await env.all(IdentityDocument, *where)


async def age_challenge(env, minutes: int):
    async with env.c.db.sessionmaker() as s, s.begin():
        conv = await s.get(Conversation, (await env.conv()).id)
        d = dict(conv.draft)
        d["selfie_challenge_at"] = (utcnow() - timedelta(minutes=minutes)).isoformat()
        conv.draft = d


# ------------------------------------------------------------------ 21. ID types per country
async def test_id_type_list_is_filtered_by_country_botswana(env):
    await env.run_registration_until("location")
    assert await env.stage() == "COLLECT_ID_DOCUMENT"
    assert env.graph.last()["interactive"]["type"] == "list"
    assert env.graph.last_buttons() == [
        "idtype_OMANG", "idtype_PASSPORT", "idtype_DRIVING_LICENCE", "idtype_none", "id_later"]
    assert "AADHAAR" not in str(env.graph.last())


async def test_id_type_list_is_filtered_by_country_india(env):
    await to_id_stage_india(env)
    assert env.graph.last_buttons() == [
        "idtype_AADHAAR_MASKED", "idtype_VOTER_ID", "idtype_PAN", "idtype_KCC", "idtype_DRIVING_LICENCE",
        "idtype_none", "id_later"]
    assert "OMANG" not in str(env.graph.last())


async def test_only_the_front_of_the_id_is_ever_requested(env):
    await to_id_stage_india(env)
    await env.button("idtype_AADHAAR_MASKED", "Aadhaar")  # masking instructions, front only
    assert "cover the first 8 digits" in env.graph.texts()[-1] and "*front*" in env.graph.texts()[-1]
    await env.identity_image()
    assert await env.stage() == "COLLECT_SELFIE"
    assert all("*back*" not in t for t in env.graph.texts())
    assert [r.kind for r in await identity_rows(env)] == ["ID_FRONT"]


async def test_front_only_id_type_moves_on_after_one_photo(env):
    await to_id_stage_india(env)
    await env.button("idtype_PAN", "PAN card")
    await env.identity_image()
    assert await env.stage() == "COLLECT_SELFIE"
    assert [r.kind for r in await identity_rows(env)] == ["ID_FRONT"]


async def test_id_type_can_be_chosen_by_typing_its_name(env):
    await env.run_registration_until("location")
    await env.text("omang")  # deterministic match, no model call (an unscripted call would fail)
    assert (await draft(env))["id_type"] == "OMANG" and "*front*" in env.graph.texts()[-1]


# ------------------------------------------------------------------ 22. accept / reject / NEEDS_HELP
async def test_id_photo_accepted_and_stored_privately(env, settings):
    await env.run_registration_until("id_type")
    await env.identity_image()
    (row,) = await identity_rows(env)
    assert (row.kind, row.id_document_type, row.status, row.country) == ("ID_FRONT", "OMANG", "ACCEPTED", "BW")
    assert row.mime_type == "image/jpeg" and len(row.sha256) == 64 and row.quality_result["width"] == 800
    # separate private storage, not the farm-photo storage, and not recorded as a farm document
    identity_root = Path(env.c.identity.storage.root)
    assert (identity_root / row.storage_key).exists()
    assert identity_root != Path(settings.media_local_dir).resolve()
    assert not (Path(settings.media_local_dir) / row.storage_key).exists()
    assert await env.all(FarmDocument) == []
    assert await env.stage() == "COLLECT_SELFIE"  # one photo is enough


async def test_low_resolution_rejected_with_one_tip_and_not_stored(env):
    await env.run_registration_until("id_type")
    await env.identity_image(size=(300, 300))
    assert await identity_rows(env) == []
    assert "too small to read" in env.graph.texts()[-1]
    assert (await draft(env))["id_attempts"] == 1 and await env.stage() == "COLLECT_ID_DOCUMENT"
    await env.identity_image()  # a good one is accepted afterwards and resets the counter
    assert len(await identity_rows(env)) == 1 and (await draft(env))["id_attempts"] == 0


async def test_wrong_mime_and_unreadable_files_rejected(env):
    await env.run_registration_until("id_type")
    await env.identity_image(mime="image/gif", data=b"GIF89a....")
    assert "JPEG or PNG" in env.graph.texts()[-1]
    await env.identity_image(data=b"\xff\xd8\xff\xe0" + b"x" * 200)  # claims JPEG but cannot be opened
    assert "couldn't open" in env.graph.texts()[-1]
    assert await identity_rows(env) == []
    assert (await draft(env))["id_attempts"] == 2


async def test_three_failures_set_needs_help_and_flow_continues(env):
    await env.run_registration_until("id_type")
    for _ in range(3):
        await env.identity_image(size=(200, 200))
    d = await draft(env)
    assert d["id_needs_help"] is True and d["id_attempts"] == 0
    assert await env.stage() == "COLLECT_SELFIE"  # moved on to the next stage
    assert "help you with this step" in env.graph.texts()[-1] or "Last step" in env.graph.texts()[-1]


async def test_i_dont_have_any_marks_needs_help(env):
    await env.run_registration_until("location")
    await env.button("idtype_none", "I don't have any")
    assert (await draft(env))["id_needs_help"] is True and await env.stage() == "COLLECT_SELFIE"


# ------------------------------------------------------------------ 23. documents
async def test_id_sent_as_pdf_document_is_accepted(env):
    await env.run_registration_until("id_type")
    await env.document()  # PDF
    (row,) = await identity_rows(env)
    assert (row.kind, row.mime_type) == ("ID_FRONT", "application/pdf")
    assert row.storage_key.endswith(".pdf") and row.quality_result["resolution_checked"] is False
    assert await env.stage() == "COLLECT_SELFIE"


async def test_id_sent_as_image_document_is_accepted(env):
    await env.run_registration_until("id_type")
    await env.document(mime="image/png")
    (row,) = await identity_rows(env)
    assert (row.kind, row.mime_type) == ("ID_FRONT", "image/png")
    (m,) = await env.all(Message, Message.type == "document", Message.content["mime_type"].as_string() == "image/png")
    assert "filename" not in m.content and "caption" not in m.content


async def test_documents_outside_the_id_stage_are_not_supported(env):
    await env.run_registration_until("address")  # COLLECT_CROPS
    await env.document()
    assert "only read text, locations and photos" in env.graph.texts()[-1]
    assert await identity_rows(env) == []
    assert any(m.type == "document" for m in await env.all(Message))  # still persisted


async def test_document_at_selfie_stage_asks_for_a_live_photo(env):
    await env.run_registration_until("id_front")
    await env.document()
    assert "front camera" in env.graph.texts()[-1] and await identity_rows(env, IdentityDocument.kind == "SELFIE") == []


async def test_image_before_choosing_id_type_is_not_saved(env):
    await env.run_registration_until("location")
    await env.identity_image()
    assert await identity_rows(env) == [] and "choose which ID card" in env.graph.texts()[-1]


# ------------------------------------------------------------------ 24. typed ID numbers
async def test_typed_id_number_is_redacted_everywhere(env, caplog):
    caplog.set_level(logging.DEBUG)
    await env.run_registration_until("location")
    await env.text("my omang is 123456789")  # no Claude call is scripted: the program handles it alone
    (m,) = await env.all(Message, Message.direction == "INBOUND", Message.content["text"].as_string().contains("omang"))
    assert "123456789" not in str(m.content) and "[ID number removed]" in m.content["text"]
    assert m.processing_status == "processed"
    assert "123456789" not in str((await draft(env)))
    assert "123456789" not in caplog.text and "123456789" not in str([b for b in env.graph.sent])
    assert "photo" in env.graph.texts()[-1] and await env.stage() == "COLLECT_ID_DOCUMENT"


async def test_typed_aadhaar_is_redacted_and_masked_photo_requested(env):
    await to_id_stage_india(env)
    await env.button("idtype_AADHAAR_MASKED", "Aadhaar")
    await env.text("1234 5678 9012")
    (m,) = await env.all(Message, Message.direction == "INBOUND", Message.content["id_number_redacted"].as_boolean() == True)  # noqa: E712
    assert "1234" not in str(m.content)
    body = env.graph.texts()[-1]
    assert "don't type ID numbers" in body and "cover the first 8 digits" in body


async def test_pan_number_and_caption_numbers_are_redacted(env):
    await env.run_registration_until("id_type")
    await env.text("ABCDE1234F")
    p = env.fixture("image")
    env._msg(p)["image"].update(id=env.add_media(), caption="aadhaar 123456789012")
    await env.post(p)
    stored = " ".join(str(m.content) for m in await env.all(Message, Message.direction == "INBOUND"))
    assert "ABCDE1234F" not in stored and "123456789012" not in stored


# ------------------------------------------------------------------ 25. reused images
async def test_reused_image_is_rejected(env):
    await env.run_registration_until("id_type")
    data = make_image()
    await env.identity_image(data=data)
    await env.identity_image(data=data)  # the same image again, as the selfie
    assert len(await identity_rows(env)) == 1
    assert "already been used" in env.graph.texts()[-1]


async def test_reuse_detection_spans_farmers(env):
    async with env.c.db.sessionmaker() as s, s.begin():
        a, b = Farmer(wa_id="+26770000001"), Farmer(wa_id="+26770000002")
        s.add_all([a, b])
    data = make_image()
    from app.enums import IdentityKind
    m1, m2 = env.add_media(data=data), env.add_media(data=data)
    async with env.c.db.sessionmaker() as s, s.begin():
        fa = (await s.execute(select(Farmer).where(Farmer.wa_id == "+26770000001"))).scalar_one()
        fb = (await s.execute(select(Farmer).where(Farmer.wa_id == "+26770000002"))).scalar_one()
        await env.c.identity.ingest(s, farmer_id=fa.id, country="BW", kind=IdentityKind.ID_FRONT,
                                    id_document_type="OMANG", media_id=m1, attempt=1)
        with pytest.raises(IdentityRejected) as e:
            await env.c.identity.ingest(s, farmer_id=fb.id, country="BW", kind=IdentityKind.ID_FRONT,
                                        id_document_type="OMANG", media_id=m2, attempt=1)
        assert e.value.reason == "duplicate"


# ------------------------------------------------------------------ 26. selfie challenge
async def test_selfie_is_asked_with_a_random_challenge_and_stored_with_it(env):
    await env.run_registration_until("id_front")
    d = await draft(env)
    n = d["selfie_challenge"]
    assert 1 <= n <= 5 and d["selfie_challenge_at"]
    assert f"*{n} finger" in env.graph.texts()[-1] and "front camera" in env.graph.texts()[-1]
    await env.identity_image()
    (row,) = await identity_rows(env, IdentityDocument.kind == "SELFIE")
    assert row.challenge == f"{n} fingers" and row.challenge_issued_at and row.id_document_type is None
    assert "selfie has been received" in env.graph.texts()[-1]
    assert (await draft(env))["selfie_doc"] == str(row.id)


async def test_expired_challenge_issues_a_new_one_and_does_not_accept_the_selfie(env):
    await env.run_registration_until("id_front")
    old = (await draft(env))["selfie_challenge"]
    await age_challenge(env, minutes=30)
    await env.identity_image()
    d = await draft(env)
    assert await identity_rows(env, IdentityDocument.kind == "SELFIE") == []
    assert d["selfie_challenge"] != old and d["selfie_doc"] is None and d["selfie_attempts"] == 0
    assert f"*{d['selfie_challenge']} finger" in env.graph.texts()[-1] and "new challenge" in env.graph.texts()[-1]
    await env.identity_image()  # within time now
    assert len(await identity_rows(env, IdentityDocument.kind == "SELFIE")) == 1


async def test_failed_selfie_gets_a_new_challenge_on_each_retry(env):
    await env.run_registration_until("id_front")
    first = (await draft(env))["selfie_challenge"]
    await env.identity_image(size=(200, 200))
    second = (await draft(env))["selfie_challenge"]
    assert second != first and f"*{second} finger" in env.graph.texts()[-1]
    await env.identity_image(size=(200, 200))
    third = (await draft(env))["selfie_challenge"]
    assert third != second
    await env.identity_image(size=(200, 200))  # third failure
    d = await draft(env)
    assert d["selfie_needs_help"] is True and await env.stage() == "COLLECT_FARM_PHOTOS"


# ------------------------------------------------------------------ 27. Send later and the submission rule
async def _submit_with(env, id_later: bool, selfie_later: bool):
    await env.run_registration_until("location")
    if id_later:
        await env.button("id_later", "Send later")
    else:
        await env.button("idtype_OMANG", "Omang")
        await env.identity_image()
    if selfie_later:
        await env.button("selfie_later", "Send later")
    else:
        await env.identity_image()
    await env.button("farmphoto_skip")
    await env.button("cropphoto_skip")
    assert await env.stage() == "REVIEW_REGISTRATION"
    summary = env.graph.texts()[-1]
    await env.button("review_confirm", "Confirm")
    return summary


async def test_photo_sent_at_review_is_refused_and_nothing_is_stored(env):
    await env.run_registration_until("crop_skip")
    assert await env.stage() == "REVIEW_REGISTRATION"
    before = (await draft(env))["farm_photo_ids"], len(await identity_rows(env))
    await env.identity_image()
    assert "can't be changed" in env.graph.texts()[-1]
    assert ((await draft(env))["farm_photo_ids"], len(await identity_rows(env))) == before
    assert await env.stage() == "REVIEW_REGISTRATION"


async def test_country_change_at_review_that_would_drop_the_id_is_refused(env):
    await env.run_registration_until("location")
    await env.button("idtype_OMANG", "Omang")
    await env.identity_image()
    await env.identity_image()
    await env.button("farmphoto_skip")
    await env.button("cropphoto_skip")
    assert await env.stage() == "REVIEW_REGISTRATION"
    env.claude.push(make_ai(Intent.CORRECT_INFORMATION, corrections=[Correction(field="country", new_value="Kenya")]))
    await env.text("change country to Kenya")
    d = await draft(env)
    assert d["country"] == "BW" and d["id_type"] == "OMANG" and d["id_front_doc"]
    assert "can't be changed" in env.graph.texts()[-1]


async def test_both_received_goes_pending_with_a_verification_record(env):
    summary = await _submit_with(env, False, False)
    assert "*ID document:* received ✅" in summary and "*Selfie:* received ✅" in summary
    f = await env.farmer()
    assert (f.registration_status, f.verification_status) == ("SUBMITTED", "PENDING")
    assert (f.id_document_status, f.selfie_status) == ("RECEIVED", "RECEIVED")
    assert len(await env.all(Verification)) == 1
    assert "pending verification" in env.graph.texts()[-1]


async def test_send_later_submits_without_verification_then_later_upload_sets_pending(env):
    summary = await _submit_with(env, True, True)
    assert "*ID document:* pending" in summary and "*Selfie:* pending" in summary
    f = await env.farmer()
    assert (f.registration_status, f.verification_status) == ("SUBMITTED", "NOT_SUBMITTED")
    assert (f.id_document_status, f.selfie_status) == ("DEFERRED", "DEFERRED")
    assert await env.all(Verification) == []
    last = env.graph.last()
    assert "still need" in env.graph.texts()[-1] and last["interactive"]["action"]["buttons"][0]["reply"]["id"] == "identity_start"

    # two days later: the farmer comes back and sends them
    await env.button("identity_start", "Send now")
    assert await env.stage() == "COLLECT_ID_DOCUMENT" and env.graph.last()["interactive"]["type"] == "list"
    await env.button("idtype_PASSPORT", "Passport")
    await env.identity_image()
    assert await env.stage() == "COLLECT_SELFIE"
    assert (await env.farmer()).verification_status == "NOT_SUBMITTED"  # still waiting for the selfie
    await env.identity_image()
    f = await env.farmer()
    assert (f.id_document_status, f.selfie_status, f.verification_status) == ("RECEIVED", "RECEIVED", "PENDING")
    assert len(await env.all(Verification)) == 1 and await env.stage() == "COMPLETED"
    assert "pending verification" in env.graph.texts()[-1]
    assert (await draft(env))["id_front_doc"] is None  # identity draft cleared after the later flow


async def test_one_item_missing_keeps_verification_not_submitted_until_it_arrives(env):
    await _submit_with(env, False, True)  # ID received, selfie later
    f = await env.farmer()
    assert (f.id_document_status, f.selfie_status, f.verification_status) == ("RECEIVED", "DEFERRED", "NOT_SUBMITTED")
    assert "selfie" in env.graph.texts()[-1] and "ID document photo" not in env.graph.texts()[-1]
    env.claude.push(make_ai(Intent.SUBMIT_IDENTITY_DOCUMENTS))  # said in words instead of tapping the button
    await env.text("I want to send my selfie now")
    assert await env.stage() == "COLLECT_SELFIE"  # only the missing item is asked
    await env.identity_image()
    f = await env.farmer()
    assert (f.selfie_status, f.verification_status) == ("RECEIVED", "PENDING")
    assert len(await env.all(Verification)) == 1


async def test_needs_help_submission_does_not_start_verification(env):
    await env.run_registration_until("location")
    await env.button("idtype_none", "I don't have any")
    await env.identity_image()
    await env.button("farmphoto_skip")
    await env.button("cropphoto_skip")
    await env.button("review_confirm")
    f = await env.farmer()
    assert (f.id_document_status, f.selfie_status, f.verification_status) == ("NEEDS_HELP", "RECEIVED", "NOT_SUBMITTED")


async def test_cancelling_the_later_flow_keeps_what_was_sent_and_defers_the_rest(env):
    await _submit_with(env, True, True)
    await env.button("identity_start", "Send now")
    env.claude.push(make_ai(Intent.CANCEL_REGISTRATION))
    await env.text("cancel")
    f = await env.farmer()
    assert f.registration_status == "SUBMITTED" and await env.stage() == "COMPLETED"
    assert (f.id_document_status, f.selfie_status) == ("DEFERRED", "DEFERRED")


# ------------------------------------------------------------------ consent / prompts
async def test_consent_text_mentions_id_photo_and_selfie(env):
    env.claude.push(make_ai(Intent.GREETING))
    await env.text("Hi")
    await env.text("Yes")
    body = env.graph.texts()[-1]
    assert "photo of your ID card and a selfie" in body and "kept private" in body and "Do you agree?" in body


async def test_asking_for_id_never_requests_a_number(env):
    await env.run_registration_until("location")
    for text in env.graph.texts()[-1:]:
        assert "number" not in text.lower().replace("never", "")
    await env.button("idtype_OMANG", "Omang")
    assert "don't type the ID number" in env.graph.texts()[-1]


# ------------------------------------------------------------------ 28. nothing identity-related reaches Claude
async def test_identity_data_never_appears_in_claude_prompts(env):
    env.claude.push(make_ai(Intent.GENERAL_QUESTION, text="We keep it private."))
    await env.run_registration_until("location")
    await env.button("idtype_OMANG", "Omang")
    await env.text("my number is 123456789")  # redacted before anything is stored or sent on
    await env.identity_image()
    await env.identity_image()
    await env.text("why do you need a selfie?")  # reaches Claude at the selfie stage
    rows = await identity_rows(env)
    secrets_ = ["123456789", "identity/", *(str(r.id) for r in rows), *(r.storage_key for r in rows),
                *(r.sha256 for r in rows), *(r.wa_media_id for r in rows)]
    assert env.claude.contexts
    for ctx in env.claude.contexts:
        blob = build_user_message(ctx) + repr(ctx)
        for s in secrets_:
            assert s not in blob
        assert ctx.collected.get("id_document") in (None, "RECEIVED", "NOT_PROVIDED")
    # history carries a placeholder for photos, never their content or reference
    assert "[sent a photo]" in repr(env.claude.contexts[-1].history)
    # all Claude traffic is text: no image data is ever attached to a Claude call
    assert not hasattr(env.claude.contexts[-1], "images")


# ------------------------------------------------------------------ 29. admin view
async def test_admin_sees_identity_status_and_metadata_but_no_storage_keys(env):
    await _submit_with(env, False, True)
    f = await env.farmer()
    r = await env.client.get("/api/admin/farmers", params={"selfie_status": "DEFERRED"}, headers=ADMIN)
    assert r.json()["total"] == 1 and r.json()["items"][0]["id_document_status"] == "RECEIVED"
    assert (await env.client.get("/api/admin/farmers", params={"selfie_status": "NEEDS_HELP"}, headers=ADMIN)).json()["total"] == 0
    body = (await env.client.get(f"/api/admin/farmers/{f.id}", headers=ADMIN)).json()
    assert sorted(d["kind"] for d in body["identity_documents"]) == ["ID_FRONT"]
    assert all(d["status"] == "ACCEPTED" and "storage_key" not in d for d in body["identity_documents"])
    assert "identity/" not in str(body)


# ------------------------------------------------------------------ 30. deletion
async def test_data_deletion_removes_identity_images_from_storage(env):
    from app.services import farmer_service
    await _submit_with(env, False, False)
    rows = await identity_rows(env)
    root = Path(env.c.identity.storage.root)
    assert len(rows) == 2 and all((root / r.storage_key).exists() for r in rows)
    f = await env.farmer()
    async with env.c.db.sessionmaker() as s, s.begin():
        farmer = await s.get(Farmer, f.id)
        with pytest.raises(RuntimeError):  # refuses to run without the service that can delete the images
            await farmer_service.anonymize_farmer(s, farmer, env.c.storage)
    async with env.c.db.sessionmaker() as s, s.begin():
        farmer = await s.get(Farmer, f.id)
        await farmer_service.anonymize_farmer(s, farmer, env.c.storage, identity=env.c.identity)
    assert not any((root / r.storage_key).exists() for r in rows)
    assert await identity_rows(env) == []
    f = await env.farmer(f"deleted:{f.id}")
    assert (f.id_document_status, f.selfie_status) == ("NOT_PROVIDED", "NOT_PROVIDED")


async def test_cancelling_registration_deletes_uploaded_identity_images(env):
    await env.run_registration_until("id_front")
    rows = await identity_rows(env)
    root = Path(env.c.identity.storage.root)
    assert rows and all((root / r.storage_key).exists() for r in rows)
    env.claude.push(make_ai(Intent.CANCEL_REGISTRATION))
    await env.text("cancel")
    await env.button("cancel_yes")
    assert await identity_rows(env) == [] and not any((root / r.storage_key).exists() for r in rows)


# ------------------------------------------------------------------ other behaviour
async def test_changing_country_discards_an_id_type_that_does_not_apply(env):
    await to_id_stage_india(env)
    await env.button("idtype_AADHAAR_MASKED", "Aadhaar")
    await env.identity_image()  # front uploaded
    from app.schemas.ai_response import Correction
    env.claude.push(make_ai(Intent.CORRECT_INFORMATION, corrections=[Correction(field="country", new_value="Botswana")]))
    await env.text("sorry, my farm is in Botswana")
    d = await draft(env)
    assert d["country"] == "BW" and d["id_type"] is None and d["id_front_doc"] is None
    (row,) = await identity_rows(env)
    assert row.status == "SUPERSEDED"
    assert env.graph.last_buttons()[0] == "idtype_OMANG"


async def test_change_id_type_button_restarts_the_id_step(env):
    await env.run_registration_until("id_type")
    await env.button("id_change", "Change ID type")
    assert (await draft(env))["id_type"] is None and env.graph.last()["interactive"]["type"] == "list"


async def test_country_without_configured_id_types_is_flagged_for_follow_up(env):
    ai = env.claude.push
    await env.run_registration_until("name")
    ai(make_ai(country="Kenya", text="What is the full address of your farm?"))
    await env.text("Kenya")
    ai(make_ai(full_address_text="Near Nakuru market, Nakuru Town East sub-county, Nakuru County", text="What crops?"))
    await env.text("Near Nakuru market, Nakuru Town East sub-county, Nakuru County")
    ai(make_ai(crops=["maize"], text="How much land?"))
    await env.text("maize")
    ai(make_ai(cultivation_area=1, area_unit="acres", text="Share the pin."))
    await env.text("1 acre")
    await env.button("loc_skip")
    assert await env.stage() == "COLLECT_SELFIE"  # no ID list for this country: ops follow up, selfie still asked
    await env.button("selfie_later")
    await env.button("farmphoto_skip")
    await env.button("cropphoto_skip")
    await env.button("review_confirm")
    f = await env.farmer()
    assert (f.id_document_status, f.verification_status) == ("NEEDS_HELP", "NOT_SUBMITTED")


async def test_reply_guard_blocks_claude_judging_identity_or_repeating_numbers():
    from app.schemas.conversation import Draft
    from app.workflows.reply_guard import check_reply
    for text, reason in [
        ("Your ID looks genuine, thank you!", "judges_identity_document"),
        ("Great, your selfie matches your ID.", "judges_identity_document"),
        ("Thanks, I noted 1234 5678 9012.", "repeats_long_number"),
    ]:
        assert check_reply(text, Draft()) == (False, reason)
    assert check_reply("Got it. Our team will check your ID and selfie.", Draft())[0]


def test_redaction_unit():
    from app.workflows.redaction import redact_id_numbers
    assert redact_id_numbers("5 acres of maize") == ("5 acres of maize", False)
    assert redact_id_numbers("2.5 hectares, 12 bags") == ("2.5 hectares, 12 bags", False)
    assert redact_id_numbers("it is 1234-5678-9012 ok")[1] and "1234" not in redact_id_numbers("1234-5678-9012")[0]
    assert redact_id_numbers("ABCDE1234F")[1] and redact_id_numbers("")[1] is False


# ------------------------------------------------------------------ migration
def _alembic(db: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db.as_posix()}"}
    root = Path(__file__).resolve().parent.parent
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=root, env=env, capture_output=True, text=True)


def _tables_and_farmer_cols(db: Path):
    import sqlite3
    with sqlite3.connect(db) as c:
        tables = {r[0] for r in c.execute("select name from sqlite_master where type='table'")}
        cols = {r[1] for r in c.execute("pragma table_info(farmers)")}
    return tables, cols


def test_migration_0002_on_a_fresh_database_is_a_no_op_after_0001(tmp_path):
    db = tmp_path / "fresh.db"
    r = _alembic(db, "upgrade", "head")
    assert r.returncode == 0, r.stderr
    tables, cols = _tables_and_farmer_cols(db)
    assert "identity_documents" in tables and {"id_document_status", "selfie_status"} <= cols
    assert _alembic(db, "upgrade", "head").returncode == 0
    assert _alembic(db, "downgrade", "0001").returncode == 0  # 0002 reverses cleanly
    tables, cols = _tables_and_farmer_cols(db)
    assert "identity_documents" not in tables and not ({"id_document_status", "selfie_status"} & cols)


def test_migration_0002_upgrades_a_database_created_before_the_feature(tmp_path):
    import sqlite3
    db = tmp_path / "old.db"
    with sqlite3.connect(db) as c:  # the pre-identity shape of the one table 0002 touches
        c.execute("create table farmers (id CHAR(32) primary key, wa_id varchar(32) not null, "
                  "registration_status varchar(20), verification_status varchar(20), "
                  "created_at datetime, updated_at datetime)")
        c.execute("insert into farmers (id, wa_id) values ('a', '+1')")
    assert _alembic(db, "stamp", "0001").returncode == 0
    r = _alembic(db, "upgrade", "head")
    assert r.returncode == 0, r.stderr
    tables, cols = _tables_and_farmer_cols(db)
    assert "identity_documents" in tables and {"id_document_status", "selfie_status"} <= cols
    with sqlite3.connect(db) as c:  # existing rows get the default
        assert c.execute("select id_document_status, selfie_status from farmers").fetchone() == ("NOT_PROVIDED",) * 2
