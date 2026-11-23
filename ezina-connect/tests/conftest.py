"""Shared test harness: sqlite DB, mocked Meta Graph API (httpx.MockTransport), scripted fake Claude."""
from __future__ import annotations

import hashlib
import hmac
import io
import itertools
import json
import os
import time
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from PIL import Image
from sqlalchemy import select

from app.config import Settings
from app.database import Base, Database
from app.enums import Intent
from app.main import create_app
from app.models import Conversation, Farm, Farmer, Message
from app.schemas.ai_response import AIResponse, ExtractedData
from app.services.claude_service import ClaudeService
from app.services.container import Container
from app.services.media_service import MediaService
from app.services.ops_notifier import OpsNotifier
from app.services.rate_limiter import RateLimiter
from app.services.storage_service import LocalStorage
from app.services.whatsapp_service import WhatsAppService

FIXTURES = Path(__file__).parent / "fixtures"
APP_SECRET = "test-app-secret"
VERIFY_TOKEN = "test-verify-token"
ADMIN_KEY = "test-admin-key"
WA_ID = "26771234567"
E164 = "+26771234567"
JPEG = b"\xff\xd8\xff\xe0" + b"x" * 200


def make_image(size=(800, 800), fmt="JPEG") -> bytes:
    """A real, decodable image that is unique on every call (identity images are checked for reuse by hash)."""
    small = Image.frombytes("RGB", (16, 16), os.urandom(16 * 16 * 3))
    buf = io.BytesIO()
    small.resize(size).save(buf, format=fmt)
    return buf.getvalue()


PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"


BW_ADDRESS = "Plot 1234, near Mogoditshane clinic, Mogoditshane, Kweneng District"


def make_ai(intent=Intent.PROVIDE_INFORMATION, *, text="", conf=0.95, lang="en", corrections=None,
            clarify=False, field_conf=None, address_missing=None, identity_choice=None, **extracted) -> AIResponse:
    return AIResponse(
        identity_choice=identity_choice,
        address_missing_parts=address_missing or [],
        intent=intent, extracted_data=ExtractedData(**extracted), corrections=corrections or [],
        confidence=conf, field_confidence=field_conf or {}, suggested_response=text, language=lang,
        requires_clarification=clarify,
    )


class FakeClaude(ClaudeService):
    """Returns scripted AIResponses in order (no network). Records the contexts it was given."""

    def __init__(self, settings):
        super().__init__(settings)
        self.script: list[AIResponse | None] = []
        self.contexts = []

    def push(self, *responses):
        self.script.extend(responses)

    async def interpret(self, ctx):
        self.contexts.append(ctx)
        if not self.script:
            raise AssertionError(f"unscripted Claude call: {ctx.message_text!r} at {ctx.stage}")
        return self.script.pop(0)


class GraphMock:
    """Mock of the Meta Graph API. Records every request; failures can be injected."""

    def __init__(self):
        self.sent: list[dict] = []
        self.requests: list[httpx.Request] = []
        self.fail_with: list[httpx.Response] = []  # popped first, one per request
        self.media: dict[str, tuple[str, bytes]] = {"MEDIA1": ("image/jpeg", JPEG)}
        self._ids = itertools.count(1)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail_with:
            return self.fail_with.pop(0)
        path = request.url.path
        if request.method == "POST" and path.endswith("/messages"):
            body = json.loads(request.content)
            if body.get("status") == "read":
                return httpx.Response(200, json={"success": True})
            self.sent.append(body)
            return httpx.Response(200, json={"messages": [{"id": f"wamid.OUT{next(self._ids)}"}]})
        if request.method == "GET" and "lookaside" in request.url.host:
            return httpx.Response(200, content=self.media[request.url.path.strip("/")][1])
        if request.method == "GET":
            media_id = path.strip("/").split("/")[-1]
            if media_id in self.media:
                mime, data = self.media[media_id]
                return httpx.Response(
                    200, json={"id": media_id, "mime_type": mime, "file_size": len(data),
                               "url": f"https://lookaside.fbsbx.com/{media_id}"},
                )
        return httpx.Response(404, json={"error": {"message": "not found", "code": 100}})

    # --- convenience
    def texts(self) -> list[str]:
        out = []
        for b in self.sent:
            if b["type"] == "text":
                out.append(b["text"]["body"])
            elif b["type"] == "interactive":
                out.append(b["interactive"]["body"]["text"])
            else:
                out.append(f"[{b['type']}]")
        return out

    def last(self) -> dict:
        return self.sent[-1]

    def last_buttons(self) -> list[str]:
        a = self.last()["interactive"]["action"]
        return [b["reply"]["id"] for b in a["buttons"]] if "buttons" in a else [r["id"] for r in a["sections"][0]["rows"]]


class Env:
    def __init__(self, app, container, graph, claude, client):
        self.app, self.c, self.graph, self.claude, self.client = app, container, graph, claude, client
        self._n = itertools.count(1)
        self._ts = int(time.time())

    # ---- webhook helpers
    @staticmethod
    def sign(body: bytes, secret: str = APP_SECRET) -> str:
        return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    def fixture(self, name: str, wa_id: str = WA_ID, msg_id: str | None = None, ts: int | None = None, **extra) -> dict:
        raw = (FIXTURES / f"{name}.json").read_text()
        raw = (raw.replace("__WA_ID__", wa_id).replace("__MSG_ID__", msg_id or f"wamid.IN{next(self._n)}")
               .replace("__TS__", str(ts or self._ts)).replace("__WAMID__", extra.get("wamid", "")))
        self._ts += 1
        return json.loads(raw)

    async def post(self, payload: dict, *, secret: str = APP_SECRET, signed: bool = True):
        body = json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"}
        if signed:
            headers["X-Hub-Signature-256"] = self.sign(body, secret)
        r = await self.c_post(body, headers)
        await self.app.state.processor.drain()
        return r

    async def c_post(self, body, headers):
        return await self.client.post("/webhook", content=body, headers=headers)

    @staticmethod
    def _msg(p: dict) -> dict:
        return p["entry"][0]["changes"][0]["value"]["messages"][0]

    async def text(self, body: str, wa_id: str = WA_ID, **kw):
        p = self.fixture("text", wa_id, **kw)
        self._msg(p)["text"]["body"] = body
        return await self.post(p)

    async def button(self, bid: str, title: str = "x", wa_id: str = WA_ID):
        p = self.fixture("interactive_button", wa_id)
        self._msg(p)["interactive"]["button_reply"] = {"id": bid, "title": title}
        return await self.post(p)

    async def location(self, wa_id: str = WA_ID, lat=-24.6282, lon=25.9231):
        p = self.fixture("location", wa_id)
        self._msg(p)["location"].update(latitude=lat, longitude=lon)
        return await self.post(p)

    async def image(self, wa_id: str = WA_ID, media_id: str = "MEDIA1", ts: int | None = None):
        p = self.fixture("image", wa_id, ts=ts)
        self._msg(p)["image"]["id"] = media_id
        return await self.post(p)

    # ---- identity (ID document / selfie) helpers
    def add_media(self, *, size=(800, 800), fmt="JPEG", mime="image/jpeg", data: bytes | None = None) -> str:
        mid = f"IDMEDIA{next(self._n)}"
        self.graph.media[mid] = (mime, data if data is not None else make_image(size, fmt))
        return mid

    async def identity_image(self, wa_id: str = WA_ID, ts: int | None = None, **kw):
        """Send a fresh, valid image (as a WhatsApp image message) unless kw says otherwise."""
        return await self.image(wa_id, self.add_media(**kw), ts=ts)

    async def document(self, wa_id: str = WA_ID, *, media_id: str | None = None, mime: str = "application/pdf",
                       data: bytes | None = None):
        if data is None and mime == "application/pdf":
            data = PDF
        fmt = {"image/png": "PNG", "image/webp": "WEBP"}.get(mime, "JPEG")
        mid = media_id or self.add_media(mime=mime, data=data, fmt=fmt)
        p = self.fixture("document", wa_id)
        self._msg(p)["document"].update(id=mid, mime_type=mime)
        return await self.post(p)

    # ---- db helpers
    async def db(self, fn):
        async with self.c.db.sessionmaker() as s:
            return await fn(s)

    async def farmer(self, wa_id: str = E164) -> Farmer | None:
        return await self._one(Farmer, Farmer.wa_id == wa_id)

    async def _one(self, model, *where):
        async with self.c.db.sessionmaker() as s:
            return (await s.execute(select(model).where(*where))).scalars().first()

    async def all(self, model, *where):
        async with self.c.db.sessionmaker() as s:
            return (await s.execute(select(model).where(*where))).scalars().all()

    async def conv(self, wa_id: str = E164) -> Conversation:
        f = await self.farmer(wa_id)
        return await self._one(Conversation, Conversation.farmer_id == f.id)

    async def stage(self, wa_id: str = E164) -> str:
        return (await self.conv(wa_id)).stage

    async def run_registration_until(self, step: str) -> None:
        """Drive the happy path up to a named point (uses scripted Claude)."""
        ai = self.claude.push
        await_steps = ["greet", "consent", "name", "country", "address", "crops", "area",
                       "location", "id_type", "id_front", "selfie", "farm_photo", "crop_skip", "confirm"]
        idx = await_steps.index(step)
        for i, s in enumerate(await_steps[: idx + 1]):
            if s == "greet":
                ai(make_ai(Intent.GREETING, conf=0.9))
                await self.text("Hi")
            elif s == "consent":
                await self.text("Yes")
                await self.button("consent_agree", "Agree")
            elif s == "name":
                ai(make_ai(full_name="John", text="Thank you, John. Which country is your farm in?"))
                await self.text("John")
            elif s == "country":
                ai(make_ai(country="Botswana", text="What is the full address of your farm?"))
                await self.text("Botswana")
            elif s == "address":
                ai(make_ai(full_address_text=BW_ADDRESS, text="What crops do you grow at the moment?"))
                await self.text(BW_ADDRESS)
            elif s == "crops":
                ai(make_ai(crops=["maize", "tomatoes"], text="About how much land do you use for farming?"))
                await self.text("Maize and tomatoes")
            elif s == "area":
                ai(make_ai(cultivation_area=5, area_unit="acres", text="Please share your farm location with the pin."))
                await self.text("5 acres")
            elif s == "location":
                await self.location()
            elif s == "id_type":
                await self.button("idtype_OMANG", "Omang")
            elif s in ("id_front", "selfie"):
                await self.identity_image()
            elif s == "farm_photo":
                await self.image()
            elif s == "crop_skip":
                await self.button("cropphoto_skip", "Skip for now")
            elif s == "confirm":
                await self.button("review_confirm", "Confirm")


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        anthropic_api_key="test", whatsapp_access_token="tok-SECRET", whatsapp_phone_number_id="PNID",
        whatsapp_verify_token=VERIFY_TOKEN, meta_app_secret=APP_SECRET, admin_api_key=ADMIN_KEY,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}", media_local_dir=str(tmp_path / "media"),
        whatsapp_retry_base_delay=0, whatsapp_max_retries=3, whatsapp_template_verification="ezina_verification",
    )


@pytest_asyncio.fixture
async def env(settings):
    graph = GraphMock()
    http = httpx.AsyncClient(transport=httpx.MockTransport(graph.handler))
    db = Database(settings.database_url)
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    wa = WhatsAppService(settings, client=http)
    storage = LocalStorage(settings.media_local_dir)
    claude = FakeClaude(settings)
    container = Container(
        settings=settings, db=db, claude=claude, whatsapp=wa, media=MediaService(settings, wa, storage),
        storage=storage, limiter=RateLimiter(settings.rate_limit_per_minute), ops=OpsNotifier(""),
    )
    app = create_app(container)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    e = Env(app, container, graph, claude, client)
    yield e
    await client.aclose()
    await http.aclose()
    await db.dispose()
