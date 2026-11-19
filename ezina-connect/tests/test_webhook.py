"""Webhook verification, signatures, parsing, persistence, dedupe, ordering, statuses (spec tests 1-8)."""
from sqlalchemy import select

from app.enums import Intent
from app.models import FarmDocument, Message
from tests.conftest import APP_SECRET, E164, VERIFY_TOKEN, WA_ID, make_ai


# 1. verification ----------------------------------------------------------------
async def test_verify_valid_token(env):
    r = await env.client.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": VERIFY_TOKEN, "hub.challenge": "1234"})
    assert r.status_code == 200 and r.text == "1234"


async def test_verify_invalid_token(env):
    r = await env.client.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "1"})
    assert r.status_code == 403


# 2. signatures ------------------------------------------------------------------
async def test_signature_invalid_missing_and_valid(env):
    p = env.fixture("text")
    assert (await env.post(p, secret="wrong")).status_code == 401
    assert (await env.post(p, signed=False)).status_code == 401
    assert await env.all(Message) == []  # nothing persisted for rejected requests
    env.claude.push(make_ai(Intent.GREETING))
    assert (await env.post(p)).status_code == 200


# 3. text ------------------------------------------------------------------------
async def test_incoming_text_persisted_normalised_and_processed(env):
    env.claude.push(make_ai(Intent.GREETING))
    p = env.fixture("text", msg_id="wamid.T1")
    assert (await env.post(p)).status_code == 200
    (m,) = await env.all(Message, Message.direction == "INBOUND")
    assert m.wa_id == E164 and m.wa_message_id == "wamid.T1" and m.type == "text"
    assert m.content["text"] == "Hi" and m.content["profile_name"] == "John M"
    assert m.processing_status == "processed"
    assert "Welcome to Ezina" in env.graph.texts()[0]
    assert (await env.farmer()).profile_name == "John M"


# 4. location --------------------------------------------------------------------
async def test_incoming_location_saved_to_draft(env):
    await env.run_registration_until("area")
    await env.location()
    conv = await env.conv()
    assert conv.draft["latitude"] == -24.6282 and conv.draft["longitude"] == 25.9231
    assert conv.stage == "COLLECT_FARM_PHOTOS"
    assert "location has been received" in env.graph.texts()[-1]


async def test_invalid_location_rejected(env):
    await env.run_registration_until("area")
    await env.location(lat=95.0, lon=10.0)
    assert (await env.conv()).draft["latitude"] is None
    assert "didn't look right" in env.graph.texts()[-1]


# 5. image + media download/storage ---------------------------------------------
async def test_incoming_image_downloaded_validated_and_stored(env, settings):
    await env.run_registration_until("location")
    await env.image()
    (doc,) = await env.all(FarmDocument)
    assert doc.doc_type == "FARM_PHOTO" and doc.mime_type == "image/jpeg" and doc.caption == "my maize"
    assert doc.size_bytes > 0 and len(doc.sha256) == 64 and doc.farm_id is None
    from pathlib import Path
    assert (Path(settings.media_local_dir) / doc.storage_key).exists()
    assert (await env.conv()).stage == "COLLECT_CROP_PHOTOS"


async def test_image_with_bad_mime_rejected(env):
    await env.run_registration_until("location")
    env.graph.media["BAD"] = ("application/pdf", b"%PDF")
    await env.image(media_id="BAD")
    assert await env.all(FarmDocument) == []
    assert "JPEG, PNG or WebP" in env.graph.texts()[-1]


async def test_image_before_consent_is_not_downloaded(env):
    env.claude.push(make_ai(Intent.GREETING))
    await env.text("Hi")
    await env.image()
    assert not [r for r in env.graph.requests if r.method == "GET"]


# 6. interactive replies ---------------------------------------------------------
async def test_button_and_list_replies(env):
    env.claude.push(make_ai(Intent.GREETING, lang="tn", conf=0.4))
    await env.text("Dumela")
    await env.text("Yes")
    await env.button("consent_agree", "Agree")
    # language unclear -> list is shown, and a list_reply is understood
    assert env.graph.last()["interactive"]["type"] == "list"
    p = env.fixture("interactive_list")
    await env.post(p)
    assert (await env.conv()).draft["preferred_language"] == "tn"
    assert (await env.stage()) == "COLLECT_NAME"


# 7. status callbacks ------------------------------------------------------------
async def test_status_callbacks_update_outbound_and_never_regress(env):
    env.claude.push(make_ai(Intent.GREETING))
    await env.text("Hi")
    (out,) = await env.all(Message, Message.direction == "OUTBOUND")
    assert out.status == "sent" and out.wa_message_id
    for name, expected in [("status_delivered", "delivered")]:
        await env.post(env.fixture(name, wamid=out.wa_message_id))
        assert (await env._one(Message, Message.id == out.id)).status == expected
    # a 'sent' arriving late must not overwrite 'delivered'
    late = env.fixture("status_delivered", wamid=out.wa_message_id)
    late["entry"][0]["changes"][0]["value"]["statuses"][0]["status"] = "sent"
    await env.post(late)
    assert (await env._one(Message, Message.id == out.id)).status == "delivered"
    await env.post(env.fixture("status_failed", wamid=out.wa_message_id))
    row = await env._one(Message, Message.id == out.id)
    assert row.status == "failed" and "131047" in row.error


# 8. duplicates ------------------------------------------------------------------
async def test_duplicate_message_processed_once(env):
    env.claude.push(make_ai(Intent.GREETING))
    p = env.fixture("text", msg_id="wamid.DUP")
    await env.post(p)
    await env.post(p)
    assert len(await env.all(Message, Message.wa_message_id == "wamid.DUP")) == 1
    assert len(env.graph.sent) == 1


# 9. out of order ----------------------------------------------------------------
async def test_older_message_arriving_late_is_ignored_for_state(env):
    await env.run_registration_until("consent")
    env.claude.push(make_ai(full_name="Newer", text="Which country?"))
    await env.text("Newer", ts=2_000_000_000)
    n_sent = len(env.graph.sent)
    # an older message (earlier WhatsApp timestamp) arrives afterwards
    env.claude.push(make_ai(full_name="Older"))
    await env.text("Older", ts=1_900_000_000)
    farmer_draft = (await env.conv()).draft
    assert farmer_draft["full_name"] == "Newer"
    assert len(env.graph.sent) == n_sent  # no reply to the stale message
    stale = await env._one(Message, Message.content["text"].as_string() == "Older")
    assert stale.processing_status == "processed"


async def test_messages_processed_in_timestamp_order_per_farmer(env):
    """Two pending messages are handled oldest-first regardless of insertion order."""
    from app.database import utcnow
    from datetime import timedelta
    env.claude.push(make_ai(Intent.GREETING))
    async with env.c.db.sessionmaker() as s, s.begin():
        base = utcnow()
        for i, (mid, ts) in enumerate([("wamid.B", base), ("wamid.A", base - timedelta(seconds=30))]):
            s.add(Message(wa_id=E164, direction="INBOUND", wa_message_id=mid, type="text",
                          content={"text": "Hi" if mid == "wamid.A" else "yes"}, wa_timestamp=ts,
                          status="received", processing_status="received"))
    env.claude.push(make_ai(Intent.GREETING))
    await env.app.state.processor.process_farmer(E164)
    done = await env.all(Message, Message.direction == "INBOUND")
    assert {m.wa_message_id: m.processing_status for m in done} == {"wamid.A": "processed", "wamid.B": "processed"}
    assert "Welcome to Ezina" in env.graph.texts()[0]  # the older 'Hi' was handled first


# unsupported types --------------------------------------------------------------
async def test_unsupported_type_persisted_and_politely_declined(env):
    await env.post(env.fixture("audio"))
    (m,) = await env.all(Message, Message.direction == "INBOUND")
    assert m.type == "audio" and m.processing_status == "processed"
    assert "only read text, locations and photos" in env.graph.texts()[0]


# recovery -----------------------------------------------------------------------
async def test_startup_recovery_reprocesses_unprocessed_messages(env):
    from app.database import utcnow
    async with env.c.db.sessionmaker() as s, s.begin():
        s.add(Message(wa_id=E164, direction="INBOUND", wa_message_id="wamid.LOST", type="text",
                      content={"text": "Hi"}, wa_timestamp=utcnow(), status="received", processing_status="processing"))
    env.claude.push(make_ai(Intent.GREETING))
    assert await env.app.state.processor.recover() == 1
    await env.app.state.processor.drain()
    m = await env._one(Message, Message.wa_message_id == "wamid.LOST")
    assert m.processing_status == "processed" and env.graph.sent


async def test_health(env):
    r = await env.client.get("/health")
    assert r.status_code == 200 and r.json()["database"] == "ok"
