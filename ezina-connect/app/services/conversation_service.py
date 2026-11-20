"""ConversationService: one inbound message -> state changes + queued outbound replies.

Rules of the road:
  * Python owns the workflow (stage, validation, statuses). Claude only interprets language and drafts text.
  * Replies are written to the outbox (messages table, status=queued) inside the same transaction as the
    state change; the processor sends them after commit.
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import aware, utcnow
from app.enums import DocumentType, IdentityKind, IdentityStatus, Intent, RegistrationStatus, Stage
from app.logging_config import mask_phone
from app.models import Conversation, Farm, Farmer, Message
from app.schemas.ai_response import AIResponse
from app.schemas.conversation import Draft, Reply
from app.services import farmer_service
from app.services.claude_service import ClaudeContext
from app.services.container import Container
from app.services.identity_service import IdentityRejected
from app.services.media_service import MediaRejected
from app.services.whatsapp_service import payloads_for_reply
from app.workflows import address_flow, identity_flow
from app.workflows import messages as M
from app.workflows import reply_guard, validators
from app.workflows.farmer_registration import FIELD_LABELS, apply_ai, apply_pending_confirmed
from app.workflows.intent_router import Action, route
from app.workflows.state_machine import (
    NEXT_FIELD,
    OPTIONAL_STAGES,
    missing_fields,
    resolve_stage,
    successor,
)

log = logging.getLogger("ezina.conversation")

SUPPORTED_INBOUND = {"text", "location", "image", "interactive", "button"}
YES_WORDS = {"yes", "y", "yeah", "yep", "ok", "okay", "sure", "agree", "i agree", "confirm", "correct", "yes please", "yebo"}
NO_WORDS = {"no", "n", "nope", "not now", "no thanks"}
SKIP_WORDS = {"skip", "later", "not now", "no photo", "skip photo", "skip for now"}
OPT_OUT_WORDS = {"stop", "unsubscribe", "opt out", "optout", "stop messages", "stop messaging"}
OPT_IN_WORDS = {"start", "subscribe", "unstop"}
# Stages whose text is always templated (legal text, data accuracy, interactive lists)
IDENTITY_STAGES = set(identity_flow.IDENTITY_STAGES)
# ID/selfie prompts are always templated: they carry the interactive ID list and the exact liveness challenge
TEMPLATE_ONLY = {
    Stage.START, Stage.CONSENT, Stage.SELECT_LANGUAGE, Stage.REVIEW_REGISTRATION,
    Stage.COLLECT_ID_DOCUMENT, Stage.COLLECT_SELFIE,
}
IN_REGISTRATION = {
    Stage.CONSENT, Stage.SELECT_LANGUAGE, Stage.COLLECT_NAME, Stage.COLLECT_COUNTRY,
    Stage.COLLECT_FARM_DETAILS, Stage.COLLECT_CROPS, Stage.COLLECT_CULTIVATION_AREA,
    Stage.COLLECT_GPS_LOCATION, Stage.COLLECT_ID_DOCUMENT, Stage.COLLECT_SELFIE,
    Stage.COLLECT_FARM_PHOTOS, Stage.COLLECT_CROP_PHOTOS, Stage.REVIEW_REGISTRATION,
}
TOPIC = {
    Stage.START: "whether they want to register their farm",
    Stage.CONSENT: "their agreement to save their details",
    Stage.SELECT_LANGUAGE: "which language they prefer",
    Stage.COLLECT_NAME: "their full name",
    Stage.COLLECT_COUNTRY: "which country their farm is in",
    Stage.COLLECT_FARM_DETAILS: "the full address of their farm, as one text (include the example for their country from address_format)",
    Stage.COLLECT_CROPS: "which crops they grow at the moment",
    Stage.COLLECT_CULTIVATION_AREA: "about how much land they use for farming (a number and a unit, e.g. 5 acres)",
    Stage.COLLECT_GPS_LOCATION: "sharing the farm location with the WhatsApp location pin (Attach, then Location); they may skip for now",
    Stage.COLLECT_ID_DOCUMENT: "sending a clear photo of their ID card (never typing the ID number); they may choose Send later",
    Stage.COLLECT_SELFIE: "sending a live selfie with their front camera; they may choose Send later",
    Stage.COLLECT_FARM_PHOTOS: "sending a photo of their farm (optional)",
    Stage.COLLECT_CROP_PHOTOS: "sending a photo of their crops (optional)",
    Stage.REVIEW_REGISTRATION: "checking their registration summary (the program shows it; just thank them)",
}


@dataclass
class Turn:
    farmer: Farmer
    conv: Conversation
    draft: Draft
    msg: Message
    content: dict
    wa_id: str
    returning: bool = False  # came back after a long pause in an unfinished registration


def _norm(text: str) -> str:
    return re.sub(r"[\s.!,]+$", "", re.sub(r"\s+", " ", (text or "").strip().lower()))


class ConversationService:
    def __init__(self, session: AsyncSession, c: Container):
        self.session, self.c, self.s = session, c, c.settings

    # ------------------------------------------------------------------ entry
    async def process(self, msg: Message) -> None:
        content = msg.content or {}
        farmer = await farmer_service.get_or_create_farmer(self.session, msg.wa_id, content.get("profile_name"))
        msg.farmer_id = farmer.id
        conv = await self._get_conversation(farmer)
        ts = aware(msg.wa_timestamp) or utcnow()

        # 24h service window is anchored on the farmer's latest inbound message
        if conv.last_inbound_at is None or ts > aware(conv.last_inbound_at):
            conv.last_inbound_at = ts
        last_done = aware(conv.last_processed_wa_ts)
        if last_done and ts < last_done:
            log.info("stale (out-of-order) message ignored", extra={"farmer": mask_phone(msg.wa_id)})
            return
        conv.last_processed_wa_ts = ts
        gap = utcnow() - aware(conv.last_interaction_at) if conv.last_interaction_at else None
        conv.last_interaction_at = utcnow()

        t = Turn(farmer, conv, Draft.model_validate(conv.draft or {}), msg, content, msg.wa_id)
        t.returning = bool(
            gap and gap > timedelta(hours=self.s.resume_greeting_after_hours) and Stage(conv.stage) in IN_REGISTRATION
        )
        try:
            if msg.wa_message_id:
                await self.c.whatsapp.mark_read(msg.wa_message_id)
            await self._dispatch(t)
        finally:
            conv.draft = t.draft.model_dump(mode="json")

    async def _get_conversation(self, farmer: Farmer) -> Conversation:
        conv = (
            await self.session.execute(select(Conversation).where(Conversation.farmer_id == farmer.id))
        ).scalar_one_or_none()
        if conv is None:
            conv = Conversation(farmer_id=farmer.id, stage=Stage.START, draft=Draft().model_dump(mode="json"))
            self.session.add(conv)
            await self.session.flush()
        return conv

    async def _dispatch(self, t: Turn) -> None:
        mtype = t.msg.type
        text = (t.content.get("text") or "").strip()

        if t.farmer.opted_out:
            if mtype == "text" and _norm(text) in OPT_IN_WORDS:
                t.farmer.opted_out, t.farmer.opted_out_at = False, None
                await self._send(t, Reply(M.OPTED_IN))
            return  # silence for opted-out farmers
        if t.conv.handoff:
            log.info("message during human handoff (bot silent)", extra={"farmer": mask_phone(t.wa_id)})
            return
        if mtype == "text" and _norm(text) in OPT_OUT_WORDS:
            return await self._opt_out(t)
        if not self.c.limiter.allow(t.wa_id):
            return await self._send(t, Reply(M.RATE_LIMITED))
        if mtype == "document":  # accepted only as an ID photo / PDF at COLLECT_ID_DOCUMENT
            return await self._on_document(t)
        if mtype not in SUPPORTED_INBOUND:
            return await self._send(t, Reply(M.UNSUPPORTED_MEDIA))

        if mtype == "location":
            return await self._on_location(t)
        if mtype == "image":
            return await self._on_image(t)
        if mtype in ("interactive", "button") and t.content.get("button_id"):
            if await self._on_button(t):
                return
        if text:
            return await self._on_text(t, text)
        await self._send(t, Reply(M.UNSUPPORTED_MEDIA))

    # ------------------------------------------------------------------ helpers
    def _cur(self, t: Turn) -> Stage:
        return Stage(t.conv.stage)

    def _resolve(self, t: Turn) -> Stage:
        if t.conv.active_flow == "identity":  # registered farmer sending the ID / selfie later
            st = identity_flow.next_identity_stage(t.draft) or Stage.COMPLETED
        else:
            st = resolve_stage(self._cur(t), t.draft, self.s.min_farm_photos)
        t.conv.stage = st
        return st

    async def _send(self, t: Turn, reply: Reply) -> None:
        for payload in payloads_for_reply(t.wa_id, reply):
            await self.c.whatsapp.queue(self.session, wa_id=t.wa_id, farmer_id=t.farmer.id, payload=payload)

    async def _send_stage(self, t: Turn, *, claude_text: str | None = None, prefix: str | None = None) -> None:
        stage = self._resolve(t)
        if stage == Stage.COLLECT_SELFIE and identity_flow.challenge_expired(
            t.draft, utcnow(), self.s.selfie_challenge_ttl_minutes
        ):
            identity_flow.issue_challenge(t.draft, utcnow())  # first prompt, or the old challenge has expired
        reply = M.stage_reply(stage, t.draft, self.s)
        if claude_text and stage not in TEMPLATE_ONLY:
            ok, why = reply_guard.check_reply(claude_text, t.draft)
            if ok and stage == Stage.COLLECT_FARM_DETAILS and (
                t.draft.address_missing or address_flow.format_for(t.draft.country).example not in claude_text
            ):  # the address question must carry Python's example for the farmer's country; follow-ups are templated
                ok, why = False, "address_example_missing"
            if ok:
                reply.body = claude_text
                prefix = None
            else:
                log.warning("claude reply rejected by guard", extra={"reason": why})
        if prefix:
            reply.body = f"{prefix}\n\n{reply.body}"
        if t.returning:  # back after a pause: greet, then continue from the next missing field
            reply.body = f"{M.welcome_back(t.draft.full_name)}\n\n{reply.body}"
            t.returning = False
        await self._send(t, reply)

    def _collected(self, d: Draft) -> dict:
        out: dict = {}
        for k in ("full_name", "country", "farm_name", "preferred_language"):
            if getattr(d, k):
                out[k] = getattr(d, k)
        if d.full_address_text and not d.address_missing:  # a partial address is not "collected" yet
            out["full_address_text"] = d.full_address_text
        if d.crops:
            out["crops"] = d.crops
        if d.cultivation_area is not None:
            out["land_size"] = M.area_display(d)
        out["location_received"] = d.has_location
        # status words only: Claude never sees identity images, numbers or anything read from them
        out["id_document"] = identity_flow.id_status(d).value
        out["selfie"] = identity_flow.selfie_status(d).value
        out["farm_photos"], out["crop_photos"] = len(d.farm_photo_ids), len(d.crop_photo_ids)
        return out

    async def _history(self, t: Turn) -> list[tuple[str, str]]:
        rows = (
            await self.session.execute(
                select(Message)
                .where(Message.wa_id == t.wa_id, Message.id != t.msg.id, Message.status != "failed")
                .order_by(Message.created_at.desc())
                .limit(self.s.history_limit)
            )
        ).scalars().all()
        out = []
        for r in reversed(rows):
            body = (r.content or {}).get("text")
            if r.type == "location":
                body = "[shared a location]"
            elif r.type == "image":
                body = "[sent a photo]"
            if body:
                out.append(("farmer" if r.direction == "INBOUND" else "ezina", body))
        return out

    async def _ask_claude(self, t: Turn, text: str, stage: Stage, mode: str = "interpret",
                          target: Stage | None = None, saved: dict | None = None) -> AIResponse | None:
        tgt = target or successor(stage)
        address = None
        if stage == Stage.COLLECT_FARM_DETAILS or tgt == Stage.COLLECT_FARM_DETAILS:
            d = t.draft  # Python picks the country's instruction, example and expected parts for Claude
            address = {**address_flow.format_for(d.country).for_claude(), "followups_asked": d.address_followups,
                       "address_so_far": d.full_address_text if d.address_missing else None,
                       "asked_for": list(d.address_missing)}
        ctx = ClaudeContext(
            stage=stage.value, next_field=NEXT_FIELD.get(stage), reply_target=TOPIC.get(tgt, "how Ezina can help (answer briefly)"),
            current_topic=TOPIC.get(stage, "the farmer's request"), collected=self._collected(t.draft),
            history=await self._history(t), message_text=text, now=utcnow(),
            preferred_language=t.draft.preferred_language or t.conv.language, mode=mode, saved_summary=saved or {},
            address=address,
        )
        return await self.c.claude.interpret(ctx)

    # ------------------------------------------------------------------ text
    async def _on_text(self, t: Turn, text: str) -> None:
        stage = self._cur(t)
        low = _norm(text)
        draft = t.draft

        if t.content.get("id_number_redacted"):  # already removed at ingest; never stored, logged or sent on
            log.info("id number redacted from farmer message", extra={"farmer": mask_phone(t.wa_id)})
            if stage in IN_REGISTRATION:
                return await self._send_stage(t, prefix=M.ID_NUMBER_REFUSED)
            return await self._send(t, Reply(M.ID_NUMBER_REFUSED))
        if stage in IDENTITY_STAGES and await self._identity_text(t, stage, low, text):
            return

        # Deterministic shortcuts for plain yes/no/skip (saves a model call; also works if Claude is down)
        expecting_yes_no = bool(draft.pending) or stage in (Stage.START, Stage.CONSENT, Stage.REVIEW_REGISTRATION)
        ai: AIResponse | None = None
        if expecting_yes_no and low in YES_WORDS:
            ai = AIResponse(intent=Intent.CONFIRM, confidence=1.0, suggested_response="")
        elif (expecting_yes_no or stage in OPTIONAL_STAGES) and low in NO_WORDS:
            ai = AIResponse(intent=Intent.DENY, confidence=1.0, suggested_response="")
        elif stage in OPTIONAL_STAGES and low in SKIP_WORDS:
            return await self._skip(t, stage)

        shortcut = ai is not None
        if ai is None:
            ai = await self._ask_claude(t, text, stage)
        if ai is None:  # Claude unavailable or invalid output twice -> safe templated message
            if stage in (Stage.START, Stage.CANCELLED, Stage.COMPLETED):
                return await self._send(t, Reply(M.FALLBACK_AI_DOWN))
            return await self._send_stage(t, prefix=M.FALLBACK_AI_DOWN)

        if not shortcut:  # only real model output says anything about the farmer's language
            if ai.language:
                t.conv.language = ai.language[:10]
            if not draft.preferred_language:
                draft.detected_language, draft.detected_language_conf = ai.language, ai.confidence

        in_reg = stage in IN_REGISTRATION
        registered = t.farmer.registration_status == RegistrationStatus.SUBMITTED
        has_data = bool(ai.extracted_data.provided() or ai.corrections)
        action = route(ai.intent, registered=registered, in_registration=in_reg, has_data=has_data)
        log.info("routed", extra={"intent": ai.intent.value, "action": action.value, "stage": stage.value})
        await self._act(t, action, ai, text, stage)

    async def _act(self, t: Turn, action: Action, ai: AIResponse, text: str, stage: Stage) -> None:
        d = t.draft
        if action == Action.OPT_OUT:
            return await self._opt_out(t)
        if action == Action.HANDOFF:
            return await self._handoff(t, "farmer asked for human support")
        if action == Action.STATUS_REGISTRATION or action == Action.STATUS_VERIFICATION:
            kind = "registration" if action == Action.STATUS_REGISTRATION else "verification"
            reply = Reply(M.status_text(t.farmer.registration_status, t.farmer.verification_status, kind))
            await self._send(t, reply)
            if stage in IN_REGISTRATION:
                await self._send_stage(t)
            return
        if action == Action.CANCEL:
            if t.conv.active_flow == "identity":  # nothing to remove: the rest simply stays for later
                return await self._cancel_identity(t)
            d.pending = {"type": "cancel"}
            return await self._send(t, M.cancel_confirm_reply())
        if action == Action.START_IDENTITY:
            if stage in IDENTITY_STAGES:
                return await self._send_stage(t)
            if stage in IN_REGISTRATION:
                return await self._send_stage(t, prefix=M.FINISH_FIRST)
            if t.farmer.registration_status != RegistrationStatus.SUBMITTED:
                return await self._send(t, Reply(M.REGISTER_FIRST))
            return await self._start_identity(t)
        if action == Action.START_REGISTRATION:
            return await self._start_registration(t, ai, stage)
        if action == Action.GREET_REGISTERED:
            return await self._send(
                t, Reply(f"Hello! 👋 {M.status_text(t.farmer.registration_status, t.farmer.verification_status, 'verification')}")
            )
        if action == Action.REGISTER_FIRST:
            t.conv.stage = Stage.START
            d.welcomed = True
            return await self._send(t, Reply(M.REGISTER_FIRST))
        if action == Action.DECLINE:  # "no" / "not now" to registering: acknowledge once, do not re-ask
            d.welcomed = True
            t.conv.stage = Stage.START
            return await self._send(t, Reply(M.NOT_NOW))
        if action == Action.NOT_YET:
            return await self._send(t, Reply(M.NOT_YET))
        if action == Action.FINISH_FIRST:
            return await self._send_stage(t, prefix=M.FINISH_FIRST)
        if action == Action.GREET_RESUME:
            t.returning = False
            return await self._send_stage(t, prefix=M.welcome_back(d.full_name))
        if action == Action.CONFIRM:
            return await self._confirm(t, stage)
        if action == Action.DENY:
            return await self._deny(t, stage)
        if action == Action.GENERAL:
            return await self._general(t, ai, stage)
        await self._answer(t, ai, text, stage)

    # ------------------------------------------------------------------ actions
    async def _start_registration(self, t: Turn, ai: AIResponse | None, stage: Stage) -> None:
        d = t.draft
        if stage in (Stage.CANCELLED, Stage.COMPLETED):
            t.draft = d = Draft()
            t.conv.stage = Stage.START
        wants = ai is not None and (
            ai.intent in (Intent.REGISTER_FARMER, Intent.CONFIRM)
            or (d.welcomed and ai.intent == Intent.PROVIDE_INFORMATION)
        )
        if wants:
            t.conv.stage = Stage.CONSENT
            t.conv.active_flow = "registration"
            return await self._send(t, M.consent_reply())
        d.welcomed = True
        t.conv.stage = Stage.START
        await self._send(t, Reply(M.WELCOME))

    async def _grant_consent(self, t: Turn) -> None:
        f, d = t.farmer, t.draft
        f.consent_given, f.consent_at = True, utcnow()
        f.registration_status = RegistrationStatus.IN_PROGRESS
        t.conv.active_flow = "registration"
        t.conv.stage = Stage.SELECT_LANGUAGE  # placeholder; resolved from the draft below
        if not d.preferred_language and d.detected_language and d.detected_language_conf >= 0.8:
            code = d.detected_language.lower()
            if code in self.s.supported_languages:
                d.preferred_language = code
        elif not d.preferred_language and (t.conv.language or "en") == "en":
            d.preferred_language = "en"
        await self._send_stage(t, prefix="Thank you!")

    async def _decline_consent(self, t: Turn) -> None:
        t.draft = Draft(welcomed=True)
        t.conv.stage = Stage.START
        await self._send(t, Reply(M.NOT_NOW))

    async def _skip(self, t: Turn, stage: Stage) -> None:
        d = t.draft
        if stage == Stage.COLLECT_GPS_LOCATION:
            d.location_skipped = True
        elif stage == Stage.COLLECT_FARM_PHOTOS:
            d.farm_photos_skipped = True
        elif stage == Stage.COLLECT_CROP_PHOTOS:
            d.crop_photos_skipped = True
        else:
            return await self._send_stage(t)
        await self._send_stage(t, prefix="No problem, you can send it later when you are at the farm.")

    async def _confirm(self, t: Turn, stage: Stage) -> None:
        d = t.draft
        pending, d.pending = d.pending, None
        if pending and pending.get("type") == "cancel":
            return await self._do_cancel(t)
        if pending and pending.get("type") == "confirm_field":
            apply_pending_confirmed(d, pending, self.s)
            return await self._send_stage(t, prefix="Thanks, saved.")
        if stage == Stage.CONSENT:
            return await self._grant_consent(t)
        if stage == Stage.REVIEW_REGISTRATION:
            return await self._submit(t)
        await self._send_stage(t)

    async def _deny(self, t: Turn, stage: Stage) -> None:
        d = t.draft
        pending, d.pending = d.pending, None
        if pending and pending.get("type") == "cancel":
            return await self._send_stage(t, prefix="Okay, let's continue.")
        if pending and pending.get("type") == "confirm_field":
            label = FIELD_LABELS.get(pending["field"], "answer")
            return await self._send_stage(t, prefix=f"No problem. Please tell me your {label} again.")
        if stage == Stage.CONSENT:
            return await self._decline_consent(t)
        if stage in OPTIONAL_STAGES:
            return await self._skip(t, stage)
        if stage == Stage.REVIEW_REGISTRATION:
            return await self._send(t, M.edit_prompt())
        await self._send_stage(t)

    async def _do_cancel(self, t: Turn) -> None:
        await farmer_service.delete_draft_documents(self.session, t.farmer.id, self.c.storage)
        if t.farmer.registration_status != RegistrationStatus.SUBMITTED:
            await self.c.identity.delete_all(self.session, t.farmer.id)  # unsubmitted ID photos / selfie go too
            t.farmer.registration_status = RegistrationStatus.CANCELLED
        t.draft = Draft()
        t.conv.stage, t.conv.active_flow = Stage.CANCELLED, None
        await self._send(t, Reply(M.CANCELLED_DONE))

    async def _opt_out(self, t: Turn) -> None:
        t.farmer.opted_out, t.farmer.opted_out_at = True, utcnow()
        log.info("farmer opted out", extra={"farmer": mask_phone(t.wa_id)})
        await self._send(t, Reply(M.OPTED_OUT))

    async def _handoff(self, t: Turn, reason: str) -> None:
        t.conv.handoff, t.conv.handoff_reason, t.conv.handoff_at = True, reason, utcnow()
        if self._cur(t) != Stage.HUMAN_HANDOFF:
            t.conv.resume_stage = t.conv.stage
        t.conv.stage = Stage.HUMAN_HANDOFF
        await self._send(t, Reply(M.HANDOFF))
        await self.c.ops.handoff(t.wa_id, reason)

    async def _submit(self, t: Turn) -> None:
        d = t.draft
        if missing_fields(d, self.s.min_farm_photos) or not d.preferred_language:
            return await self._send_stage(t)
        await farmer_service.submit_registration(self.session, t.farmer, d)
        t.draft = Draft()
        t.conv.stage, t.conv.active_flow = Stage.COMPLETED, None
        # verification (PENDING) starts only when both the ID document and the selfie were received
        await self._send(t, M.submitted_reply(d.id_received, d.selfie_received))

    async def _general(self, t: Turn, ai: AIResponse, stage: Stage) -> None:
        in_reg = stage in IN_REGISTRATION
        ok, _ = reply_guard.check_reply(ai.suggested_response, t.draft)
        if ok and ai.suggested_response:
            await self._send(t, Reply(ai.suggested_response))
        else:
            await self._send(t, Reply("I'm here to help with your Ezina registration."))
        if in_reg:
            await self._send_stage(t)
        elif stage != Stage.COMPLETED and t.farmer.registration_status != RegistrationStatus.SUBMITTED:
            await self._send(t, Reply("Would you like to register your farm? It's free."))

    async def _answer(self, t: Turn, ai: AIResponse, text: str, stage: Stage) -> None:
        d = t.draft
        if stage == Stage.CONSENT:  # no personal data is saved before explicit consent
            return await self._send(t, M.consent_reply())
        d.pending = None
        before = self._resolve(t)
        old_country = d.country
        result = apply_ai(d, ai, before, self.s)
        if (
            before == Stage.REVIEW_REGISTRATION and "country" in result.changed and d.id_type
            and identity_flow.find_type(d.country, d.id_type) is None
        ):  # changing the country would wipe the ID document, which cannot be edited at review
            d.country = old_country
            return await self._send(t, Reply(M.REVIEW_COUNTRY_LOCKED))
        if "country" in result.changed:
            await self._reset_id_if_country_changed(t)
        if result.confirm:
            d.pending = result.confirm
            label = FIELD_LABELS.get(result.confirm["field"], "answer")
            shown = result.confirm["value"]
            if isinstance(shown, tuple):
                shown = f"{shown[0]:g} {shown[1] or ''}".strip()
            elif isinstance(shown, list):
                shown = ", ".join(shown)
            return await self._send(t, M.confirm_field_reply(label, str(shown)))
        after = self._resolve(t)

        if result.errors and not result.changed:
            e = result.errors[0]
            example = address_flow.format_for(d.country).example if e.field == "full_address_text" else e.example
            return await self._send(t, M.validation_error_reply(e.field, example))

        # Typed address / coordinates instead of a WhatsApp location pin
        substantive = [f for f in result.changed if f != "farm_name"]
        if before == Stage.COLLECT_GPS_LOCATION and not d.has_location and not substantive:
            return await self._send(t, Reply(M.ADDRESS_NOT_GPS, buttons=M.location_prompt().buttons))
        if before in (Stage.COLLECT_FARM_PHOTOS, Stage.COLLECT_CROP_PHOTOS) and after == before and not substantive:
            return await self._send_stage(t, prefix="I didn't receive a photo.")

        if before == Stage.COLLECT_FARM_DETAILS and d.address_missing and "full_address_text" not in result.changed:
            # the missing part was not given: ask again, or after 2 follow-ups accept the address as it is
            address_flow.no_answer_followup(d)
            return await self._send_stage(t, prefix=None if d.address_missing else "Okay, I'll keep the address as you gave it.")

        if not substantive:
            text_ok = ai.requires_clarification and ai.suggested_response
            return await self._send_stage(t, claude_text=ai.suggested_response if text_ok else None,
                                          prefix=None if text_ok else "Sorry, I didn't quite catch that.")

        if before == Stage.REVIEW_REGISTRATION:
            return await self._send_stage(t, prefix="Done, I've updated that.")

        if after == Stage.COLLECT_FARM_DETAILS and d.address_missing:
            return await self._send_stage(t)  # follow-up for the missing address parts (templated, already says thanks)

        claude_text: str | None = None
        if after not in TEMPLATE_ONLY:
            if after == before:  # still on the same question: template is exact
                claude_text = None
            elif after == successor(before) and not ai.requires_clarification:
                claude_text = ai.suggested_response
            else:  # multi-answer jump etc.: ask Claude to word the reply for the real next step
                saved = {k: getattr(d, k, None) for k in result.changed if k != "cultivation_area"}
                if "cultivation_area" in result.changed:
                    saved["land_size"] = M.area_display(d)
                composed = await self._ask_claude(t, text, before, mode="compose", target=after, saved=saved)
                claude_text = composed.suggested_response if composed else None
        await self._send_stage(t, claude_text=claude_text, prefix="Thank you!")

    # ------------------------------------------------------------------ buttons
    async def _on_button(self, t: Turn) -> bool:
        """Handle known interactive ids. Returns False if the id is unknown (fall back to title text)."""
        bid, stage, d = t.content["button_id"], self._cur(t), t.draft
        if bid == M.BTN_CONSENT_YES:
            await (self._grant_consent(t) if stage == Stage.CONSENT else self._send_stage(t))
        elif bid == M.BTN_CONSENT_NO:
            await (self._decline_consent(t) if stage == Stage.CONSENT else self._send_stage(t))
        elif bid.startswith(M.LANG_PREFIX):
            code = bid[len(M.LANG_PREFIX):]
            if stage == Stage.SELECT_LANGUAGE and code in self.s.supported_languages:
                d.preferred_language = code
                await self._send_stage(t, prefix="Thank you!")
            else:
                await self._send_stage(t)
        elif bid in (M.BTN_LOC_SKIP, M.BTN_FARMPHOTO_SKIP, M.BTN_CROPPHOTO_SKIP):
            expected = {
                M.BTN_LOC_SKIP: Stage.COLLECT_GPS_LOCATION,
                M.BTN_FARMPHOTO_SKIP: Stage.COLLECT_FARM_PHOTOS,
                M.BTN_CROPPHOTO_SKIP: Stage.COLLECT_CROP_PHOTOS,
            }[bid]
            await (self._skip(t, stage) if stage == expected else self._send_stage(t))
        elif bid == M.BTN_REVIEW_CONFIRM:
            await (self._submit(t) if stage == Stage.REVIEW_REGISTRATION else self._send_stage(t))
        elif bid == M.BTN_REVIEW_EDIT:
            await (self._send(t, M.edit_prompt()) if stage == Stage.REVIEW_REGISTRATION else self._send_stage(t))
        elif bid == M.BTN_REVIEW_CANCEL:
            d.pending = {"type": "cancel"}
            await self._send(t, M.cancel_confirm_reply())
        elif bid in (M.BTN_YES, M.BTN_NO):
            await (self._confirm(t, stage) if bid == M.BTN_YES else self._deny(t, stage))
        elif bid.startswith(M.IDTYPE_PREFIX) or bid in (M.BTN_ID_LATER, M.BTN_SELFIE_LATER, M.BTN_ID_CHANGE):
            await self._on_identity_button(t, bid)
        elif bid == M.BTN_IDENTITY_START:
            if stage == Stage.COMPLETED and t.farmer.registration_status == RegistrationStatus.SUBMITTED:
                await self._start_identity(t)
            else:
                await self._send_stage(t) if stage in IN_REGISTRATION else await self._send(t, Reply(M.REGISTER_FIRST))
        elif bid in (M.BTN_CANCEL_YES, M.BTN_CANCEL_NO):
            if bid == M.BTN_CANCEL_YES:
                await self._do_cancel(t)
            else:
                d.pending = None
                await self._send_stage(t, prefix="Okay, let's continue.")
        else:
            return False
        return True

    # ------------------------------------------------------------------ location / photos
    async def _latest_farm(self, t: Turn) -> Farm | None:
        return (
            await self.session.execute(
                select(Farm).where(Farm.farmer_id == t.farmer.id).order_by(Farm.created_at.desc()).limit(1)
            )
        ).scalars().first()

    async def _on_location(self, t: Turn) -> None:
        stage, c, d = self._cur(t), t.content, t.draft
        try:
            lat, lon = validators.validate_lat_lon(c.get("latitude"), c.get("longitude"))
        except validators.ValidationFailure:
            return await self._send(t, M.location_prompt("Sorry, that location didn't look right. "))

        if stage == Stage.COMPLETED or t.conv.active_flow == "identity":  # at the farm later: shares the pin
            farm = await self._latest_farm(t)
            if farm is None:
                return await self._send(t, Reply(M.NOT_YET))
            farm.latitude, farm.longitude = lat, lon
            farm.location_name, farm.location_address = c.get("location_name"), c.get("location_address")
            await self._send(t, Reply("Thank you! Your farm location has been saved. 📍"))
            if t.conv.active_flow == "identity":  # keep going with the ID / selfie
                await self._send_stage(t)
            return
        if stage == Stage.CONSENT:
            return await self._send(t, M.consent_reply())
        if stage not in IN_REGISTRATION:
            return await self._send(t, Reply(M.REGISTER_FIRST))
        d.latitude, d.longitude = lat, lon
        d.location_name, d.location_address = c.get("location_name"), c.get("location_address")
        d.location_skipped = False
        await self._send_stage(t, prefix="Thank you! Your farm location has been received. ✅")

    async def _on_image(self, t: Turn) -> None:
        stage, c, d = self._cur(t), t.content, t.draft
        if stage == Stage.CONSENT:
            return await self._send(t, M.consent_reply())
        if stage not in IN_REGISTRATION and stage != Stage.COMPLETED:
            return await self._send(t, Reply(M.REGISTER_FIRST))
        if stage == Stage.SELECT_LANGUAGE:
            return await self._send_stage(t)
        if stage in IDENTITY_STAGES:  # ID card / selfie: private storage, never saved as a farm photo
            return await self._on_identity_media(t)
        if stage == Stage.REVIEW_REGISTRATION:  # at review only text details can be edited, never ID / selfie / photos
            return await self._send(t, Reply(M.REVIEW_NO_MEDIA_EDIT))
        doc_type = DocumentType.CROP_PHOTO if stage == Stage.COLLECT_CROP_PHOTOS else DocumentType.FARM_PHOTO
        farm = await self._latest_farm(t) if stage == Stage.COMPLETED else None
        try:
            doc = await self.c.media.ingest_image(
                self.session, farmer_id=t.farmer.id, media_id=c["media_id"], doc_type=doc_type,
                caption=c.get("caption"), farm_id=farm.id if farm else None,
            )
        except MediaRejected as e:
            return await self._send(t, Reply(e.user_message))
        if stage == Stage.COMPLETED:
            return await self._send(t, Reply("Thank you! Your photo has been added to your farm. 📷"))
        (d.crop_photo_ids if doc_type == DocumentType.CROP_PHOTO else d.farm_photo_ids).append(str(doc.id))
        await self._send_stage(t, prefix="Got it! Photo received. 📷")

    # ---------------------------------------------------------------------- identity (ID document + selfie)
    async def _on_document(self, t: Turn) -> None:
        """WhatsApp 'document' messages: an ID as image/PDF at COLLECT_ID_DOCUMENT only; unsupported elsewhere."""
        stage = self._cur(t)
        if stage == Stage.COLLECT_ID_DOCUMENT:
            return await self._on_identity_media(t)
        if stage == Stage.COLLECT_SELFIE:
            return await self._send_stage(t, prefix=M.SELFIE_NOT_FILE)
        await self._send(t, Reply(M.UNSUPPORTED_MEDIA))

    async def _on_identity_media(self, t: Turn) -> None:
        stage, d, c = self._cur(t), t.draft, t.content
        challenge = challenge_at = None
        if stage == Stage.COLLECT_ID_DOCUMENT:
            if not d.id_type:
                return await self._send_stage(t, prefix=M.ID_FIRST_CHOOSE_TYPE)  # not saved as the wrong kind
            kind, attempt = (IdentityKind.ID_BACK if d.id_front_doc else IdentityKind.ID_FRONT), d.id_attempts + 1
        else:
            kind, attempt = IdentityKind.SELFIE, d.selfie_attempts + 1
            arrived = aware(t.msg.wa_timestamp) or utcnow()
            if identity_flow.challenge_expired(d, arrived, self.s.selfie_challenge_ttl_minutes):
                identity_flow.issue_challenge(d, utcnow())  # too late: the new challenge replaces the old one
                return await self._send_stage(t, prefix=M.SELFIE_NEW_CHALLENGE)
            challenge, challenge_at = d.selfie_challenge, d.selfie_challenge_at
        try:
            doc = await self.c.identity.ingest(
                self.session, farmer_id=t.farmer.id, country=d.country or t.farmer.country, kind=kind,
                id_document_type=d.id_type if kind != IdentityKind.SELFIE else None, media_id=c["media_id"],
                attempt=attempt, challenge=challenge, challenge_issued_at=challenge_at,
            )
        except IdentityRejected as e:
            return await self._identity_failed(t, kind, e)
        if kind == IdentityKind.SELFIE:
            d.selfie_doc, d.selfie_attempts = str(doc.id), 0
            return await self._identity_next(t, "Thank you, your selfie has been received ✅.")
        if kind == IdentityKind.ID_FRONT:
            d.id_front_doc = str(doc.id)
        else:
            d.id_back_doc = str(doc.id)
        d.id_attempts = 0
        await self._identity_next(t, "Got it ✅.")

    async def _identity_failed(self, t: Turn, kind: IdentityKind, e: IdentityRejected) -> None:
        """One main thing to fix; after IDENTITY_MAX_ATTEMPTS the item becomes NEEDS_HELP and the flow moves on."""
        d, selfie = t.draft, kind == IdentityKind.SELFIE
        if e.counts_as_attempt:
            n = (d.selfie_attempts if selfie else d.id_attempts) + 1
            if selfie:
                d.selfie_attempts = n
            else:
                d.id_attempts = n
            if n >= self.s.identity_max_attempts:
                if selfie:
                    d.selfie_needs_help, d.selfie_attempts = True, 0
                else:
                    d.id_needs_help, d.id_attempts = True, 0
                log.warning("identity needs help", extra={
                    "farmer": mask_phone(t.wa_id), "item": "selfie" if selfie else "id_document", "reason": e.reason})
                return await self._identity_next(t, f"{e.user_message}\n\n{M.ID_NEEDS_HELP}")
            if selfie:
                identity_flow.issue_challenge(d, utcnow())  # a new challenge on every retry
        await self._send_stage(t, prefix=e.user_message)

    async def _identity_text(self, t: Turn, stage: Stage, low: str, text: str) -> bool:
        """Deterministic text answers at the ID / selfie stages. True when handled (no model call needed)."""
        d = t.draft
        if low in SKIP_WORDS or low == "send later":
            if stage == Stage.COLLECT_ID_DOCUMENT:
                d.id_deferred = True
            else:
                d.selfie_deferred = True
            await self._identity_next(t, M.ID_DEFERRED)
            return True
        if stage == Stage.COLLECT_ID_DOCUMENT and not d.id_type:
            it = identity_flow.match_type_text(d.country or t.farmer.country, text)
            if it:
                identity_flow.select_type(d, it)
                await self._send_stage(t)
                return True
        return False

    async def _on_identity_button(self, t: Turn, bid: str) -> None:
        stage, d = self._cur(t), t.draft
        if bid == M.BTN_ID_LATER and stage == Stage.COLLECT_ID_DOCUMENT:
            d.id_deferred = True
            return await self._identity_next(t, M.ID_DEFERRED)
        if bid == M.BTN_SELFIE_LATER and stage == Stage.COLLECT_SELFIE:
            d.selfie_deferred = True
            return await self._identity_next(t, M.ID_DEFERRED)
        if stage != Stage.COLLECT_ID_DOCUMENT:  # stale button from an earlier message
            return await self._send_stage(t)
        if bid == M.IDTYPE_NONE:  # "I don't have any of these": operations follow up
            d.id_needs_help = True
            log.warning("identity needs help", extra={"farmer": mask_phone(t.wa_id), "item": "id_document", "reason": "no_id"})
            return await self._identity_next(t, M.ID_NEEDS_HELP)
        if bid == M.BTN_ID_CHANGE:
            await self.c.identity.supersede(self.session, t.farmer.id, IdentityKind.ID_FRONT)
            identity_flow.reset_id(d)
            return await self._send_stage(t)
        if bid.startswith(M.IDTYPE_PREFIX):
            it = identity_flow.find_type(d.country or t.farmer.country, bid[len(M.IDTYPE_PREFIX):])
            if it:
                identity_flow.select_type(d, it)
        await self._send_stage(t)

    async def _reset_id_if_country_changed(self, t: Turn) -> None:
        d = t.draft
        if d.id_type and identity_flow.find_type(d.country, d.id_type) is None:  # that ID is not valid in the new country
            await self.c.identity.supersede(self.session, t.farmer.id, IdentityKind.ID_FRONT)
            identity_flow.reset_id(d)

    async def _identity_next(self, t: Turn, prefix: str | None = None) -> None:
        if t.conv.active_flow == "identity" and identity_flow.next_identity_stage(t.draft) is None:
            return await self._finish_identity(t, prefix)
        await self._send_stage(t, prefix=prefix)

    async def _start_identity(self, t: Turn) -> None:
        """SUBMIT_IDENTITY_DOCUMENTS: a registered farmer sends the missing ID document and/or selfie later."""
        f = t.farmer
        docs = await self.c.identity.accepted(self.session, f.id)
        d = Draft(country=f.country, preferred_language=f.preferred_language)
        front, back, selfie = docs.get("ID_FRONT"), docs.get("ID_BACK"), docs.get("SELFIE")
        if f.id_document_status == IdentityStatus.RECEIVED and front:
            d.id_type, d.id_front_doc, d.id_back_required = front.id_document_type, str(front.id), back is not None
            d.id_back_doc = str(back.id) if back else None
        if f.selfie_status == IdentityStatus.RECEIVED and selfie:
            d.selfie_doc = str(selfie.id)
        if identity_flow.next_identity_stage(d) is None:
            return await self._send(t, Reply(M.IDENTITY_ALREADY))
        t.draft, t.conv.active_flow = d, "identity"
        await self._send_stage(t)

    async def _finish_identity(self, t: Turn, prefix: str | None = None) -> None:
        d, f = t.draft, t.farmer
        id_s, sf_s = identity_flow.id_status(d), identity_flow.selfie_status(d)
        opened = await farmer_service.complete_identity(self.session, f, id_s, sf_s)
        t.draft, t.conv.stage, t.conv.active_flow = Draft(), Stage.COMPLETED, None
        both = id_s == IdentityStatus.RECEIVED and sf_s == IdentityStatus.RECEIVED
        text = M.IDENTITY_COMPLETE if opened else (M.IDENTITY_ALREADY if both else M.IDENTITY_PARTIAL)
        await self._send(t, Reply(f"{prefix}\n\n{text}" if prefix else text))

    async def _cancel_identity(self, t: Turn) -> None:
        """'cancel' during the later ID/selfie flow: whatever is not sent yet stays for later."""
        d = t.draft
        if not identity_flow.id_resolved(d):
            d.id_deferred = True
        if not identity_flow.selfie_resolved(d):
            d.selfie_deferred = True
        await self._finish_identity(t, "Okay, no problem.")


# ---------------------------------------------------------------------- admin helpers
async def release_handoff(session: AsyncSession, farmer_id: uuid.UUID) -> bool:
    conv = (await session.execute(select(Conversation).where(Conversation.farmer_id == farmer_id))).scalar_one_or_none()
    if conv is None or not conv.handoff:
        return False
    conv.handoff, conv.handoff_reason = False, None
    conv.stage = conv.resume_stage or Stage.START
    conv.resume_stage = None
    return True
