"""WhatsApp outbound behaviour, 24h window, retries, admin API (spec tests 18-20)."""
from datetime import timedelta

import httpx
from sqlalchemy import select

from app.database import utcnow
from app.models import Conversation, Message, Verification
from app.services.whatsapp_service import (
    TEXT_LIMIT, buttons_payload, list_payload, split_text, template_payload,
)
from tests.conftest import ADMIN_KEY, E164, WA_ID

H = {"X-API-Key": ADMIN_KEY}


# payload builders -----------------------------------------------------------------------
def test_text_split_respects_limit_and_loses_nothing():
    text = ("word " * 2000).strip()
    parts = split_text(text)
    assert len(parts) > 1 and all(len(p) <= TEXT_LIMIT for p in parts)
    assert " ".join(parts).split() == text.split()
    assert split_text("short") == ["short"]


def test_interactive_payload_limits():
    p = buttons_payload("+26771234567", "x" * 2000, [("a", "A very long button title indeed"), ("b", "B"), ("c", "C"), ("d", "D")])
    assert len(p["interactive"]["body"]["text"]) == 1024 and len(p["interactive"]["action"]["buttons"]) == 3
    assert len(p["interactive"]["action"]["buttons"][0]["reply"]["title"]) <= 20
    assert p["to"] == "26771234567"
    rows = [(f"r{i}", "T" * 40, None) for i in range(15)]
    lp = list_payload("+1", "body", "Choose", rows)
    assert len(lp["interactive"]["action"]["sections"][0]["rows"]) == 10


def test_template_payload():
    p = template_payload("+26771234567", "ezina_update", "en", ["hello"])
    assert p["template"]["components"][0]["parameters"][0]["text"] == "hello"


# 19. send errors / retry ----------------------------------------------------------------
async def _send(env, **body):
    return await env.client.post("/api/whatsapp/send", json=body, headers=H)


async def _open_window(env, wa_id=E164):
    from app.models import Farmer
    async with env.c.db.sessionmaker() as s, s.begin():
        f = Farmer(wa_id=wa_id)
        s.add(f)
        await s.flush()
        s.add(Conversation(farmer_id=f.id, stage="COMPLETED", draft={}, last_inbound_at=utcnow()))
    return f.id


async def test_send_retries_on_429_and_5xx_with_backoff_then_succeeds(env):
    await _open_window(env)
    env.graph.fail_with = [httpx.Response(429, json={"error": {"code": 130429, "message": "rate"}}, headers={"retry-after": "0"}),
                           httpx.Response(503, json={"error": {"message": "unavailable"}})]
    r = await _send(env, to=WA_ID, text="hi")
    assert r.json()["status"] == "sent" and len(env.graph.sent) == 1
    assert len(env.graph.requests) == 3  # 2 failures + success


async def test_send_gives_up_after_max_retries(env):
    await _open_window(env)
    env.graph.fail_with = [httpx.Response(500, json={"error": {"message": "boom"}})] * 5
    r = await _send(env, to=WA_ID, text="hi")
    assert r.json()["status"] == "failed" and len(env.graph.requests) == env.c.settings.whatsapp_max_retries
    row = (await env.all(Message, Message.direction == "OUTBOUND"))[0]
    assert row.status == "failed" and row.wa_message_id is None


async def test_expired_token_is_not_retried_and_never_logged(env, caplog):
    await _open_window(env)
    env.graph.fail_with = [httpx.Response(401, json={"error": {"code": 190, "message": "Error validating access token"}})] * 5
    with caplog.at_level("DEBUG"):
        r = await _send(env, to=WA_ID, text="hi")
    assert r.json()["status"] == "failed" and len(env.graph.requests) == 1  # no endless retry
    assert any("token rejected" in rec.message for rec in caplog.records)
    assert "tok-SECRET" not in caplog.text


async def test_client_error_is_not_retried(env):
    await _open_window(env)
    env.graph.fail_with = [httpx.Response(400, json={"error": {"code": 131009, "message": "Parameter invalid"}})] * 3
    r = await _send(env, to=WA_ID, text="hi")
    assert r.json()["status"] == "failed" and len(env.graph.requests) == 1


# 18. 24-hour window + template fallback ------------------------------------------------
async def test_free_text_outside_window_without_template_is_blocked_not_sent(env):
    fid = await _open_window(env)
    async with env.c.db.sessionmaker() as s, s.begin():
        c = (await s.execute(select(Conversation))).scalars().one()
        c.last_inbound_at = utcnow() - timedelta(hours=25)
    r = await _send(env, to=WA_ID, text="hello")
    assert r.json()["status"] == "failed" and "24h" in r.json()["error"]
    assert env.graph.sent == []


async def test_outside_window_explicit_template_is_sent(env):
    await _open_window(env)
    async with env.c.db.sessionmaker() as s, s.begin():
        (await s.execute(select(Conversation))).scalars().one().last_inbound_at = utcnow() - timedelta(hours=30)
    r = await _send(env, to=WA_ID, template={"name": "ezina_update", "language": "en", "params": ["x"]})
    assert r.json()["status"] == "sent" and env.graph.last()["type"] == "template"


async def test_inside_window_text_is_sent_and_persisted_with_wamid(env):
    await _open_window(env)
    r = await _send(env, to=WA_ID, text="hello")
    assert r.json()["status"] == "sent"
    row = (await env.all(Message, Message.direction == "OUTBOUND"))[0]
    assert row.wa_message_id == r.json()["wa_message_id"] and row.content["text"] == "hello"


async def test_send_api_requires_key_and_valid_body(env):
    assert (await env.client.post("/api/whatsapp/send", json={"to": WA_ID, "text": "x"})).status_code == 401
    assert (await env.client.post("/api/whatsapp/send", json={"to": WA_ID, "text": "x"}, headers={"X-API-Key": "bad"})).status_code == 401
    assert (await _send(env, to="abc", text="x")).status_code == 422
    assert (await _send(env, to=WA_ID)).status_code == 422
    assert (await _send(env, to=WA_ID, text="x", template={"name": "t"})).status_code == 422


async def test_admin_disabled_when_key_not_configured(env):
    env.c.settings.admin_api_key = type(env.c.settings.admin_api_key)("")
    r = await env.client.get("/api/admin/farmers", headers=H)
    assert r.status_code == 503


# 20. admin verification + notification ---------------------------------------------------
async def _registered(env):
    await env.run_registration_until("confirm")
    return (await env.farmer()).id


async def test_admin_list_and_view_farmer(env):
    fid = await _registered(env)
    r = await env.client.get("/api/admin/farmers", params={"verification_status": "PENDING"}, headers=H)
    assert r.json()["total"] == 1 and r.json()["items"][0]["full_name"] == "John"
    assert (await env.client.get("/api/admin/farmers", params={"verification_status": "VERIFIED"}, headers=H)).json()["total"] == 0
    d = (await env.client.get(f"/api/admin/farmers/{fid}", headers=H)).json()
    assert d["farms"][0]["crops"][0]["name"] == "maize" and len(d["documents"]) == 1
    assert d["conversation"]["stage"] == "COMPLETED" and d["verification_history"][0]["status"] == "PENDING"


async def test_admin_verify_updates_status_history_and_notifies_in_window(env):
    fid = await _registered(env)
    before = len(env.graph.sent)
    r = await env.client.post(f"/api/admin/farmers/{fid}/verification",
                              json={"status": "VERIFIED", "notes": "Site visit done", "reviewer": "ops1"}, headers=H)
    assert r.status_code == 200 and r.json()["verification_status"] == "VERIFIED"
    assert (await env.farmer()).verification_status == "VERIFIED"
    hist = await env.all(Verification, Verification.farmer_id == fid)
    assert [h.status for h in hist].count("VERIFIED") == 1 and {h.reviewer for h in hist} >= {"ops1"}
    assert len(env.graph.sent) == before + 1
    assert env.graph.last()["type"] == "text" and "verified" in env.graph.texts()[-1].lower()


async def test_admin_verify_outside_window_uses_template(env):
    fid = await _registered(env)
    async with env.c.db.sessionmaker() as s, s.begin():
        (await s.execute(select(Conversation))).scalars().one().last_inbound_at = utcnow() - timedelta(days=3)
    r = await env.client.post(f"/api/admin/farmers/{fid}/verification", json={"status": "NEEDS_MORE_INFO", "notes": "Photo unclear"}, headers=H)
    assert r.status_code == 200
    sent = env.graph.last()
    assert sent["type"] == "template" and sent["template"]["name"] == "ezina_verification"
    assert "Photo unclear" in sent["template"]["components"][0]["parameters"][0]["text"]


async def test_admin_cannot_verify_unsubmitted_farmer_or_use_invalid_status(env):
    await env.run_registration_until("country")
    fid = (await env.farmer()).id
    r = await env.client.post(f"/api/admin/farmers/{fid}/verification", json={"status": "VERIFIED"}, headers=H)
    assert r.status_code == 409
    r = await env.client.post(f"/api/admin/farmers/{fid}/verification", json={"status": "PENDING"}, headers=H)
    assert r.status_code == 422


async def test_opted_out_farmer_is_not_notified(env):
    fid = await _registered(env)
    await env.text("STOP")
    before = len(env.graph.sent)
    await env.client.post(f"/api/admin/farmers/{fid}/verification", json={"status": "REJECTED"}, headers=H)
    assert len(env.graph.sent) == before


async def test_handoff_release(env):
    from app.enums import Intent
    from tests.conftest import make_ai
    await env.run_registration_until("country")
    env.claude.push(make_ai(Intent.REQUEST_HUMAN_SUPPORT))
    await env.text("human please")
    fid = (await env.farmer()).id
    assert (await env.client.post(f"/api/admin/farmers/{fid}/handoff/release", headers=H)).status_code == 200
    conv = await env.conv()
    assert not conv.handoff and conv.stage == "COLLECT_FARM_DETAILS"
    assert (await env.client.post(f"/api/admin/farmers/{fid}/handoff/release", headers=H)).status_code == 409


async def test_anonymise_farmer_removes_personal_data(env):
    from app.services import farmer_service
    from app.models import FarmDocument, Farm
    fid = await _registered(env)
    async with env.c.db.sessionmaker() as s, s.begin():
        f = await s.get(type(await env.farmer()), fid)
        await farmer_service.anonymize_farmer(s, f, env.c.storage, identity=env.c.identity)
    f = await env.farmer(f"deleted:{fid}")
    assert f.full_name is None and f.deleted_at and f.anonymized_at and f.opted_out
    assert await env.all(FarmDocument) == []
    assert (await env.all(Farm))[0].latitude is None


async def test_log_masking():
    from app.logging_config import mask_phone, scrub
    assert mask_phone("+26771234567") == "+26******567"
    s = scrub("to 26771234567 with Bearer abc.def-123 and access_token=XYZ123")
    assert "26771234567" not in s and "abc.def" not in s and "XYZ123" not in s
