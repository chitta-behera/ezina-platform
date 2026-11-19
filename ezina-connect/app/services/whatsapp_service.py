"""Meta WhatsApp Cloud API client: payload builders, retrying sender, outbox delivery, media download."""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database import aware, utcnow
from app.enums import DeliveryStatus
from app.logging_config import mask_phone
from app.models import Conversation, Message
from app.schemas.conversation import Reply

log = logging.getLogger("ezina.whatsapp")

TEXT_LIMIT = 4096
WINDOW = timedelta(hours=24)
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
AUTH_ERROR_CODES = {190, 102, 10}  # expired / invalid token, permission


class WhatsAppError(Exception):
    def __init__(self, message: str, status: int | None = None, code: int | None = None):
        super().__init__(message)
        self.status, self.code = status, code


class WhatsAppAuthError(WhatsAppError):
    """Token expired/invalid. Never retried; must be fixed by an operator."""


_last_created = utcnow()


def _next_created_at():
    """Strictly increasing timestamps so queued replies are always sent in the order they were written
    (coarse clocks, e.g. on Windows, can otherwise produce ties)."""
    global _last_created
    now = utcnow()
    _last_created = now if now > _last_created else _last_created + timedelta(microseconds=1)
    return _last_created


# ---------------------------------------------------------------- payload builders (pure)
def split_text(text: str, limit: int = TEXT_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    rest = text
    while len(rest) > limit:
        cut = max(rest.rfind("\n\n", 0, limit), rest.rfind("\n", 0, limit), rest.rfind(" ", 0, limit))
        if cut < limit // 2:
            cut = limit
        parts.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        parts.append(rest)
    return parts


def text_payload(to: str, body: str) -> dict:
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to.lstrip("+"),
        "type": "text",
        "text": {"preview_url": False, "body": body},
    }


def buttons_payload(to: str, body: str, buttons: list[tuple[str, str]]) -> dict:
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to.lstrip("+"),
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body[:1024]},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": bid, "title": title[:20]}} for bid, title in buttons[:3]
                ]
            },
        },
    }


def list_payload(to: str, body: str, button_label: str, rows: list[tuple[str, str, str | None]]) -> dict:
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to.lstrip("+"),
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": body[:1024]},
            "action": {
                "button": button_label[:20],
                "sections": [
                    {
                        "title": "Options",
                        "rows": [
                            {"id": rid, "title": title[:24], **({"description": d[:72]} if d else {})}
                            for rid, title, d in rows[:10]
                        ],
                    }
                ],
            },
        },
    }


def image_payload(to: str, link: str, caption: str | None = None) -> dict:
    img: dict = {"link": link}
    if caption:
        img["caption"] = caption[:1024]
    return {"messaging_product": "whatsapp", "to": to.lstrip("+"), "type": "image", "image": img}


def template_payload(to: str, name: str, language: str, body_params: list[str] | None = None) -> dict:
    tpl: dict = {"name": name, "language": {"code": language}}
    if body_params:
        tpl["components"] = [
            {"type": "body", "parameters": [{"type": "text", "text": p} for p in body_params]}
        ]
    return {"messaging_product": "whatsapp", "to": to.lstrip("+"), "type": "template", "template": tpl}


def payloads_for_reply(to: str, reply: Reply) -> list[dict]:
    """One Reply -> one or more API payloads (text is split at 4096 chars)."""
    if reply.list_rows:
        return [list_payload(to, reply.body, reply.list_button_label,
                             [(r.id, r.title, r.description) for r in reply.list_rows])]
    if reply.buttons:
        return [buttons_payload(to, reply.body, [(b.id, b.title) for b in reply.buttons])]
    return [text_payload(to, part) for part in split_text(reply.body)]


# ---------------------------------------------------------------- service
class WhatsAppService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.s = settings
        self.base = f"https://graph.facebook.com/{settings.whatsapp_graph_api_version}"
        self.client = client or httpx.AsyncClient(timeout=20.0)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.s.whatsapp_access_token.get_secret_value()}"}

    async def _request(self, method: str, url: str, **kw) -> httpx.Response:
        delay = self.s.whatsapp_retry_base_delay
        last: Exception | None = None
        for attempt in range(1, self.s.whatsapp_max_retries + 1):
            try:
                resp = await self.client.request(method, url, headers=self._headers(), **kw)
            except (httpx.TransportError, httpx.TimeoutException) as e:
                last = WhatsAppError(f"network error: {type(e).__name__}")
            else:
                if resp.status_code < 400:
                    return resp
                code, msg = _error_info(resp)
                if resp.status_code == 401 or code in AUTH_ERROR_CODES:
                    log.critical("WhatsApp access token rejected - rotate WHATSAPP_ACCESS_TOKEN", extra={"code": code})
                    raise WhatsAppAuthError(msg, resp.status_code, code)
                if resp.status_code not in _RETRYABLE_STATUS:
                    raise WhatsAppError(msg, resp.status_code, code)
                last = WhatsAppError(msg, resp.status_code, code)
                retry_after = resp.headers.get("retry-after")
                if retry_after and retry_after.isdigit():
                    delay = max(delay, float(retry_after))
            if attempt < self.s.whatsapp_max_retries:
                log.warning("WhatsApp request failed, retrying", extra={"attempt": attempt})
                await asyncio.sleep(delay)
                delay *= 2
        raise last or WhatsAppError("request failed")

    async def send_payload(self, payload: dict) -> str:
        """POST a messages payload; return the WhatsApp message id (wamid)."""
        url = f"{self.base}/{self.s.whatsapp_phone_number_id}/messages"
        resp = await self._request("POST", url, json=payload)
        data = resp.json()
        try:
            return data["messages"][0]["id"]
        except (KeyError, IndexError, TypeError) as e:
            raise WhatsAppError("unexpected send response") from e

    async def mark_read(self, wa_message_id: str) -> None:
        try:
            url = f"{self.base}/{self.s.whatsapp_phone_number_id}/messages"
            await self._request(
                "POST", url, json={"messaging_product": "whatsapp", "status": "read", "message_id": wa_message_id}
            )
        except WhatsAppError as e:  # best effort only
            log.warning("mark_read failed", extra={"error": str(e)})

    async def get_media_meta(self, media_id: str) -> dict:
        resp = await self._request("GET", f"{self.base}/{media_id}")
        return resp.json()

    async def download_media(self, url: str) -> bytes:
        resp = await self._request("GET", url)
        return resp.content

    # ---- outbox
    async def in_service_window(self, session: AsyncSession, farmer_id) -> bool:
        if farmer_id is None:
            return False
        conv = (await session.execute(select(Conversation).where(Conversation.farmer_id == farmer_id))).scalar_one_or_none()
        last = aware(conv.last_inbound_at) if conv else None
        return bool(last and utcnow() - last < WINDOW)

    async def queue(
        self,
        session: AsyncSession,
        *,
        wa_id: str,
        farmer_id,
        payload: dict,
        fallback_template: dict | None = None,
    ) -> Message:
        content = {"text": _payload_text(payload)}
        if fallback_template:
            content["fallback_template"] = fallback_template
        row = Message(
            farmer_id=farmer_id, wa_id=wa_id, direction="OUTBOUND", type=payload["type"],
            content=content, payload=payload, status=DeliveryStatus.QUEUED, processing_status="processed",
            wa_timestamp=utcnow(), created_at=_next_created_at(),
        )
        session.add(row)
        await session.flush()
        return row

    async def deliver(self, session: AsyncSession, row: Message) -> None:
        """Send one queued outbound row, honouring the 24h window. Never raises for API failures."""
        payload = row.payload or {}
        row.attempts += 1
        try:
            replying_now = (row.content or {}).get("in_window")  # direct reply to a just-received message
            if payload.get("type") != "template" and not replying_now and not await self.in_service_window(session, row.farmer_id):
                tpl = (row.content or {}).get("fallback_template")
                if not tpl:
                    row.status, row.error = DeliveryStatus.FAILED, "outside_24h_window_no_template"
                    log.warning("outbound blocked: outside 24h window", extra={"to": mask_phone(row.wa_id)})
                    return
                payload = template_payload(row.wa_id, tpl["name"], tpl["language"], tpl.get("params"))
                row.payload, row.type = payload, "template"
            row.wa_message_id = await self.send_payload(payload)
            row.status, row.error = DeliveryStatus.SENT, None
        except WhatsAppAuthError as e:
            row.status, row.error = DeliveryStatus.FAILED, f"auth: {e}"
        except WhatsAppError as e:
            row.status, row.error = DeliveryStatus.FAILED, str(e)[:500]
            log.error("outbound send failed", extra={"to": mask_phone(row.wa_id), "error": str(e)[:200]})
        finally:
            await session.flush()


def _payload_text(payload: dict) -> str:
    t = payload.get("type")
    if t == "text":
        return payload["text"]["body"]
    if t == "interactive":
        return payload["interactive"]["body"]["text"]
    if t == "image":
        return payload["image"].get("caption", "")
    if t == "template":
        return f"[template:{payload['template']['name']}]"
    return ""


def _error_info(resp: httpx.Response) -> tuple[int | None, str]:
    try:
        err = resp.json().get("error", {})
        return err.get("code"), re.sub(r"\s+", " ", str(err.get("message", resp.text)))[:300]
    except Exception:
        return None, resp.text[:300]
