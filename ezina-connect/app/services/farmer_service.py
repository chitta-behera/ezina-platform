"""Farmer persistence: get-or-create, submission, verification, anonymisation."""
from __future__ import annotations

import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database import utcnow
from app.enums import IdentityStatus, RegistrationStatus, VerificationStatus
from app.models import Farm, FarmDocument, Farmer, FarmerCrop, IdentityDocument, Message, Verification
from app.schemas.conversation import Draft
from app.workflows import identity_flow
from app.workflows.validators import normalize_crop


async def get_or_create_farmer(session: AsyncSession, wa_id: str, profile_name: str | None) -> Farmer:
    farmer = (await session.execute(select(Farmer).where(Farmer.wa_id == wa_id))).scalar_one_or_none()
    if farmer is None:
        farmer = Farmer(wa_id=wa_id, profile_name=profile_name)
        session.add(farmer)
        await session.flush()
    elif profile_name and farmer.profile_name != profile_name:
        farmer.profile_name = profile_name
    return farmer


async def submit_registration(session: AsyncSession, farmer: Farmer, draft: Draft) -> Farm:
    """Materialise the draft into farmer/farm/crops, link photos, and open verification (PENDING)."""
    farmer.full_name = draft.full_name
    farmer.country = draft.country
    farmer.preferred_language = draft.preferred_language
    farmer.registration_status = RegistrationStatus.SUBMITTED
    farmer.id_document_status = identity_flow.id_status(draft).value
    farmer.selfie_status = identity_flow.selfie_status(draft).value
    # Verification starts only when BOTH the ID document and the selfie have been received.
    identity_complete = draft.id_received and draft.selfie_received
    farmer.verification_status = (
        VerificationStatus.PENDING if identity_complete else VerificationStatus.NOT_SUBMITTED
    )

    farm = Farm(
        farmer_id=farmer.id, name=draft.farm_name, full_address_text=draft.full_address_text or "",
        latitude=draft.latitude, longitude=draft.longitude,
        location_name=draft.location_name, location_address=draft.location_address,
        cultivation_area=draft.cultivation_area, area_unit=draft.area_unit, area_hectares=draft.area_hectares,
    )
    session.add(farm)
    await session.flush()

    crop_rows = []
    for raw in draft.crops:
        c = FarmerCrop(farm_id=farm.id, name_raw=raw, name_normalized=normalize_crop(raw))
        session.add(c)
        crop_rows.append(c)
    await session.flush()

    doc_ids = [uuid.UUID(x) for x in draft.farm_photo_ids + draft.crop_photo_ids]
    if doc_ids:
        docs = (await session.execute(select(FarmDocument).where(FarmDocument.id.in_(doc_ids)))).scalars().all()
        for d in docs:
            d.farm_id = farm.id

    if identity_complete:
        session.add(Verification(farmer_id=farmer.id, status=VerificationStatus.PENDING, notes="Submitted via WhatsApp"))
    await session.flush()
    return farm


async def complete_identity(
    session: AsyncSession, farmer: Farmer, id_status: IdentityStatus, selfie_status: IdentityStatus
) -> bool:
    """Later upload (SUBMIT_IDENTITY_DOCUMENTS): update the identity statuses; open verification once both are
    RECEIVED. Returns True when verification just moved to PENDING."""
    farmer.id_document_status, farmer.selfie_status = id_status.value, selfie_status.value
    both = id_status == IdentityStatus.RECEIVED and selfie_status == IdentityStatus.RECEIVED
    if both and farmer.registration_status == RegistrationStatus.SUBMITTED and farmer.verification_status in (
        VerificationStatus.NOT_SUBMITTED, VerificationStatus.NEEDS_MORE_INFO
    ):
        farmer.verification_status = VerificationStatus.PENDING
        session.add(Verification(farmer_id=farmer.id, status=VerificationStatus.PENDING,
                                 notes="Identity documents received after registration"))
        await session.flush()
        return True
    return False


async def record_verification(
    session: AsyncSession, farmer: Farmer, status: VerificationStatus, reviewer: str | None, notes: str | None
) -> Verification:
    farmer.verification_status = status
    row = Verification(farmer_id=farmer.id, status=status, reviewer=reviewer, notes=notes)
    session.add(row)
    await session.flush()
    return row


async def delete_draft_documents(session: AsyncSession, farmer_id: uuid.UUID, storage) -> None:
    """Remove un-submitted photos (farm_id IS NULL) from DB and storage, e.g. on cancellation."""
    docs = (
        await session.execute(
            select(FarmDocument).where(FarmDocument.farmer_id == farmer_id, FarmDocument.farm_id.is_(None))
        )
    ).scalars().all()
    for d in docs:
        await storage.delete(d.storage_key)
    if docs:
        await session.execute(delete(FarmDocument).where(FarmDocument.id.in_([d.id for d in docs])))


async def anonymize_farmer(session: AsyncSession, farmer: Farmer, storage, identity=None) -> None:
    """Data-deletion request: strip personal data, delete media, keep an inert audit shell.

    `identity` (the IdentityService) hard-deletes ID photos and selfies from the private identity storage; it is
    required whenever the farmer has any, so images can never be left behind.
    """
    if identity is not None:
        await identity.delete_all(session, farmer.id)
    elif (await session.execute(select(IdentityDocument.id).where(IdentityDocument.farmer_id == farmer.id))).first():
        raise RuntimeError("anonymize_farmer needs the identity service to delete this farmer's identity images")
    farmer.id_document_status = farmer.selfie_status = IdentityStatus.NOT_PROVIDED.value
    docs = (await session.execute(select(FarmDocument).where(FarmDocument.farmer_id == farmer.id))).scalars().all()
    for d in docs:
        await storage.delete(d.storage_key)
    await session.execute(delete(FarmDocument).where(FarmDocument.farmer_id == farmer.id))
    farms = (await session.execute(select(Farm).where(Farm.farmer_id == farmer.id))).scalars().all()
    for f in farms:
        f.name = f.location_name = f.location_address = None
        f.full_address_text = ""  # NOT NULL column: erased, not removed
        f.latitude = f.longitude = None
    # the audit log keeps the shape of the conversation but not its personal content
    await session.execute(
        update(Message).where(Message.farmer_id == farmer.id)
        .values(wa_id=f"deleted:{farmer.id}", content={}, payload=None)
    )
    farmer.wa_id = f"deleted:{farmer.id}"
    farmer.profile_name = farmer.full_name = farmer.country = None
    farmer.opted_out = True
    farmer.deleted_at = farmer.anonymized_at = utcnow()
