"""Operations/admin endpoints (ADMIN_API_KEY). Only humans on the Ezina team can verify a farmer."""
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_container, get_session, require_admin
from app.enums import IdentityStatus, RegistrationStatus, VerificationStatus
from app.models import Conversation, Farm, FarmDocument, Farmer, FarmerCrop, IdentityDocument, Message, Verification
from app.services import farmer_service
from app.services.container import Container
from app.services.conversation_service import release_handoff
from app.services.whatsapp_service import template_payload, text_payload
from app.workflows import messages as M

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)], tags=["admin"])


def _farmer_row(f: Farmer) -> dict:
    return {
        "id": str(f.id), "wa_id": f.wa_id, "full_name": f.full_name, "country": f.country,
        "preferred_language": f.preferred_language, "registration_status": f.registration_status,
        "verification_status": f.verification_status, "opted_out": f.opted_out,
        "id_document_status": f.id_document_status, "selfie_status": f.selfie_status,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


@router.get("/farmers")
async def list_farmers(
    registration_status: RegistrationStatus | None = None,
    verification_status: VerificationStatus | None = None,
    id_document_status: IdentityStatus | None = None,
    selfie_status: IdentityStatus | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    q = select(Farmer).where(Farmer.deleted_at.is_(None))
    if registration_status:
        q = q.where(Farmer.registration_status == registration_status.value)
    if verification_status:
        q = q.where(Farmer.verification_status == verification_status.value)
    if id_document_status:  # e.g. NEEDS_HELP -> field follow-up
        q = q.where(Farmer.id_document_status == id_document_status.value)
    if selfie_status:
        q = q.where(Farmer.selfie_status == selfie_status.value)
    total = (await session.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (await session.execute(q.order_by(Farmer.created_at.desc()).limit(limit).offset(offset))).scalars().all()
    return {"total": total, "items": [_farmer_row(f) for f in rows]}


@router.get("/farmers/{farmer_id}")
async def get_farmer(farmer_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    f = await session.get(Farmer, farmer_id)
    if f is None:
        raise HTTPException(404, "farmer not found")
    farms = (await session.execute(select(Farm).where(Farm.farmer_id == f.id))).scalars().all()
    farm_out = []
    for farm in farms:
        crops = (await session.execute(select(FarmerCrop).where(FarmerCrop.farm_id == farm.id))).scalars().all()
        farm_out.append({
            "id": str(farm.id), "name": farm.name, "full_address_text": farm.full_address_text,
            "latitude": farm.latitude, "longitude": farm.longitude,
            "cultivation_area": farm.cultivation_area, "area_unit": farm.area_unit, "area_hectares": farm.area_hectares,
            "crops": [{"id": str(c.id), "name": c.name_raw, "normalized": c.name_normalized} for c in crops],
        })
    docs = (await session.execute(select(FarmDocument).where(FarmDocument.farmer_id == f.id))).scalars().all()
    # identity images: metadata only (no storage key, no URL). Viewing them is a separate, audited step (phase 2).
    ident = (await session.execute(select(IdentityDocument).where(IdentityDocument.farmer_id == f.id).order_by(IdentityDocument.created_at))).scalars().all()
    conv = (await session.execute(select(Conversation).where(Conversation.farmer_id == f.id))).scalar_one_or_none()
    history = (await session.execute(select(Verification).where(Verification.farmer_id == f.id).order_by(Verification.created_at))).scalars().all()
    recent = (
        await session.execute(select(Message).where(Message.farmer_id == f.id).order_by(Message.created_at.desc()).limit(30))
    ).scalars().all()
    return {
        **_farmer_row(f), "profile_name": f.profile_name, "consent_given": f.consent_given,
        "consent_at": f.consent_at.isoformat() if f.consent_at else None,
        "farms": farm_out,
        "documents": [
            {"id": str(d.id), "type": d.doc_type, "storage_key": d.storage_key, "mime": d.mime_type,
             "size": d.size_bytes, "sha256": d.sha256, "caption": d.caption, "farm_id": str(d.farm_id) if d.farm_id else None}
            for d in docs
        ],
        "identity_documents": [
            {"id": str(d.id), "kind": d.kind, "id_document_type": d.id_document_type, "status": d.status,
             "mime": d.mime_type, "size": d.size_bytes, "attempt": d.attempt, "challenge": d.challenge,
             "quality_result": d.quality_result, "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None}
            for d in ident
        ],
        "conversation": None if conv is None else {
            "stage": conv.stage, "active_flow": conv.active_flow, "handoff": conv.handoff,
            "handoff_reason": conv.handoff_reason,
            "last_inbound_at": conv.last_inbound_at.isoformat() if conv.last_inbound_at else None,
        },
        "verification_history": [
            {"status": v.status, "reviewer": v.reviewer, "notes": v.notes, "at": v.created_at.isoformat()} for v in history
        ],
        "recent_messages": [
            {"direction": m.direction, "type": m.type, "text": (m.content or {}).get("text"), "status": m.status,
             "at": m.created_at.isoformat()} for m in reversed(recent)
        ],
    }


class VerificationUpdate(BaseModel):
    status: Literal["VERIFIED", "REJECTED", "NEEDS_MORE_INFO"]
    notes: str | None = Field(None, max_length=1000)
    reviewer: str | None = Field(None, max_length=200)


@router.post("/farmers/{farmer_id}/verification")
async def update_verification(
    farmer_id: uuid.UUID, body: VerificationUpdate,
    session: AsyncSession = Depends(get_session), c: Container = Depends(get_container),
):
    f = await session.get(Farmer, farmer_id)
    if f is None:
        raise HTTPException(404, "farmer not found")
    if f.registration_status != RegistrationStatus.SUBMITTED:
        raise HTTPException(409, "farmer has not submitted a registration")
    await farmer_service.record_verification(session, f, VerificationStatus(body.status), body.reviewer, body.notes)

    notified: str | None = None
    if not f.opted_out:
        text = M.verification_notification(body.status, body.notes)
        fallback = None
        if c.settings.whatsapp_template_verification:
            fallback = {
                "name": c.settings.whatsapp_template_verification,
                "language": c.settings.whatsapp_template_language,
                "params": [text],
            }
        row = await c.whatsapp.queue(
            session, wa_id=f.wa_id, farmer_id=f.id, payload=text_payload(f.wa_id, text), fallback_template=fallback
        )
        await c.whatsapp.deliver(session, row)  # text inside the 24h window, otherwise template (or fails visibly)
        notified = row.status if row.status != "sent" else f"sent:{row.type}"
        if row.error:
            notified = f"{row.status}: {row.error}"
    return {"farmer_id": str(f.id), "verification_status": f.verification_status, "notification": notified}


@router.post("/farmers/{farmer_id}/handoff/release")
async def release(farmer_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    if not await release_handoff(session, farmer_id):
        raise HTTPException(409, "farmer is not in human handoff")
    return {"farmer_id": str(farmer_id), "handoff": False}
