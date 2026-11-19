"""Internal outbound API. Protected by ADMIN_API_KEY; never expose without it."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_container, get_session, require_admin
from app.models import Farmer
from app.schemas.whatsapp import to_e164
from app.services.container import Container
from app.services.whatsapp_service import template_payload, text_payload

router = APIRouter(prefix="/api/whatsapp", dependencies=[Depends(require_admin)], tags=["whatsapp"])


class TemplateSpec(BaseModel):
    name: str
    language: str = "en"
    params: list[str] = Field(default_factory=list)


class SendRequest(BaseModel):
    to: str
    text: str | None = Field(None, max_length=16000)
    template: TemplateSpec | None = None


class SendResponse(BaseModel):
    message_id: str
    status: Literal["sent", "failed"]
    wa_message_id: str | None = None
    error: str | None = None


@router.post("/send", response_model=SendResponse)
async def send_message(
    req: SendRequest, session: AsyncSession = Depends(get_session), c: Container = Depends(get_container)
):
    if bool(req.text) == bool(req.template):
        raise HTTPException(422, "provide exactly one of 'text' or 'template'")
    try:
        wa_id = to_e164(req.to)
    except ValueError:
        raise HTTPException(422, "invalid phone number") from None

    farmer = (await session.execute(select(Farmer).where(Farmer.wa_id == wa_id))).scalar_one_or_none()
    if farmer and farmer.opted_out:
        raise HTTPException(409, "recipient has opted out of messaging")

    if req.template:
        payload = template_payload(wa_id, req.template.name, req.template.language, req.template.params)
    else:
        payload = text_payload(wa_id, req.text or "")
    row = await c.whatsapp.queue(session, wa_id=wa_id, farmer_id=farmer.id if farmer else None, payload=payload)
    await c.whatsapp.deliver(session, row)
    return SendResponse(
        message_id=str(row.id), status="sent" if row.status == "sent" else "failed",
        wa_message_id=row.wa_message_id, error=row.error,
    )
