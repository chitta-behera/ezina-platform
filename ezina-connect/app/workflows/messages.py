"""Deterministic (templated) farmer-facing messages. Used as the safe fallback for Claude replies,
and always for legal / data-accuracy messages (consent, review summary, statuses)."""
from __future__ import annotations

from app.config import Settings
from app.enums import Stage, VerificationStatus
from app.schemas.conversation import Button, Draft, ListRow, Reply
from app.workflows.validators import UNIT_LABEL, country_name

# ids of interactive replies handled deterministically by Python
BTN_CONSENT_YES, BTN_CONSENT_NO = "consent_agree", "consent_no"
BTN_LOC_SKIP = "loc_skip"
BTN_FARMPHOTO_SKIP = "farmphoto_skip"
BTN_CROPPHOTO_SKIP = "cropphoto_skip"
BTN_REVIEW_CONFIRM, BTN_REVIEW_EDIT, BTN_REVIEW_CANCEL = "review_confirm", "review_edit", "review_cancel"
BTN_YES, BTN_NO = "confirm_yes", "confirm_no"
BTN_CANCEL_YES, BTN_CANCEL_NO = "cancel_yes", "cancel_no"
LANG_PREFIX = "lang_"

WELCOME = (
    "Welcome to Ezina! 🌱 We help farmers connect with buyers looking for produce. "
    "Would you like to register your farm? It's free."
)

UNSUPPORTED_MEDIA = (
    "Sorry, I can only read text, locations and photos for now. "
    "Please send your answer as a text message."
)

FALLBACK_AI_DOWN = "Sorry, I'm having a little trouble understanding right now. Let's try again."


def consent_reply() -> Reply:
    return Reply(
        body=(
            "Great! To register, we'll save your name, farm details, location and photos "
            "so buyers can find you. Do you agree?"
        ),
        buttons=[Button(BTN_CONSENT_YES, "Agree"), Button(BTN_CONSENT_NO, "Not now")],
    )


def language_reply(settings: Settings) -> Reply:
    rows = [ListRow(f"{LANG_PREFIX}{code}", name[:24]) for code, name in settings.supported_languages.items()]
    return Reply(body="Which language would you like to use?", list_rows=rows[:10], list_button_label="Languages")


def _crops_display(crops: list[str]) -> str:
    return ", ".join(c[:1].upper() + c[1:] for c in crops)


def area_display(draft: Draft) -> str:
    if draft.cultivation_area is None or not draft.area_unit:
        return ""
    return f"{draft.cultivation_area:g} {UNIT_LABEL.get(draft.area_unit, draft.area_unit)}"


def stage_reply(stage: Stage, draft: Draft, settings: Settings) -> Reply:
    """Default question for a stage."""
    if stage == Stage.START:
        return Reply(WELCOME)
    if stage == Stage.CONSENT:
        return consent_reply()
    if stage == Stage.SELECT_LANGUAGE:
        return language_reply(settings)
    if stage == Stage.COLLECT_NAME:
        return Reply("May I know your full name?")
    if stage == Stage.COLLECT_COUNTRY:
        return Reply("Which country is your farm in?")
    if stage == Stage.COLLECT_FARM_DETAILS:
        if draft.village and not draft.district:
            return Reply(f"Which district is {draft.village} in?")
        if draft.district and not draft.village:
            return Reply(f"Which village or town in {draft.district} is your farm in?")
        return Reply("Which village and district is your farm in?")
    if stage == Stage.COLLECT_CROPS:
        return Reply("What crops do you grow at the moment?")
    if stage == Stage.COLLECT_CULTIVATION_AREA:
        return Reply("About how much land do you use for farming? For example: *5 acres* or *2 hectares*.")
    if stage == Stage.COLLECT_GPS_LOCATION:
        return location_prompt()
    if stage == Stage.COLLECT_FARM_PHOTOS:
        return photo_prompt("farm", BTN_FARMPHOTO_SKIP)
    if stage == Stage.COLLECT_CROP_PHOTOS:
        return photo_prompt("crops", BTN_CROPPHOTO_SKIP)
    if stage == Stage.REVIEW_REGISTRATION:
        return review_reply(draft)
    return Reply("How can I help you today?")


# Optional steps (location, farm photo, crop photo) are all asked the same way:
# how to send it with the 📎 button + a single "Skip for now" button.
SKIP_LABEL = "Skip for now"


def photo_prompt(what: str, skip_id: str) -> Reply:
    return Reply(
        body=(
            f"Please send a photo of your {what}: tap 📎 (Attach) → Camera or Gallery. "
            "You can skip for now and send it later when you are at the farm."
        ),
        buttons=[Button(skip_id, SKIP_LABEL)],
    )


def location_prompt(extra: str = "") -> Reply:
    return Reply(
        body=(
            f"{extra}Please share your farm location: tap 📎 (Attach) → Location → "
            "*Send your current location*, ideally while you are at the farm. "
            "You can skip for now and share it later when you are there."
        ).strip(),
        buttons=[Button(BTN_LOC_SKIP, SKIP_LABEL)],
    )


def review_reply(draft: Draft) -> Reply:
    lines = ["Here is your registration summary:"]
    lines.append(f"*Name:* {draft.full_name}")
    lines.append(f"*Country:* {country_name(draft.country)}")
    lines.append(f"*Village/Town:* {draft.village}, {draft.district} district")
    if draft.farm_name:
        lines.append(f"*Farm name:* {draft.farm_name}")
    lines.append(f"*Crops:* {_crops_display(draft.crops)}")
    lines.append(f"*Land:* {area_display(draft)}")
    lines.append("*Location:* received ✅" if draft.has_location else "*Location:* not shared yet")
    n_farm, n_crop = len(draft.farm_photo_ids), len(draft.crop_photo_ids)
    photos = []
    if n_farm:
        photos.append(f"{n_farm} farm photo{'s' if n_farm != 1 else ''}")
    if n_crop:
        photos.append(f"{n_crop} crop photo{'s' if n_crop != 1 else ''}")
    lines.append(f"*Photos:* {', '.join(photos) if photos else 'none yet'}")
    lines.append("")
    lines.append("Is everything correct?")
    return Reply(
        body="\n".join(lines),
        buttons=[Button(BTN_REVIEW_CONFIRM, "Confirm"), Button(BTN_REVIEW_EDIT, "Edit"), Button(BTN_REVIEW_CANCEL, "Cancel")],
    )


def edit_prompt() -> Reply:
    return Reply("Sure! What would you like to change? For example: _change land to 4 hectares_.")


def confirm_field_reply(field_label: str, value_text: str) -> Reply:
    return Reply(
        f"Just to be sure: your {field_label} is *{value_text}*. Is that right?",
        buttons=[Button(BTN_YES, "Yes"), Button(BTN_NO, "No")],
    )


def cancel_confirm_reply() -> Reply:
    return Reply(
        "Do you want to stop your registration? Your saved answers will be removed.",
        buttons=[Button(BTN_CANCEL_YES, "Yes, cancel"), Button(BTN_CANCEL_NO, "No, continue")],
    )


def validation_error_reply(field: str, example: str) -> Reply:
    nice = {
        "full_name": "your name",
        "country": "the country",
        "village": "the village or town",
        "district": "the district",
        "crops": "your crops",
        "cultivation_area": "the land size",
        "area_unit": "the land size",
        "preferred_language": "the language",
    }.get(field, "that")
    return Reply(f"Sorry, I couldn't understand {nice}. Please try again, for example: *{example}*")


ADDRESS_NOT_GPS = (
    "Thank you, I've noted that. To save the exact farm location I need the WhatsApp location pin "
    "(please don't type coordinates): tap 📎 (Attach) → Location → *Send your current location*."
)

REGISTERED_SUBMITTED = (
    "Thank you for registering with Ezina. Your farmer registration has been submitted and is pending "
    "verification. Our team will contact you once the verification process is complete."
)
CANCELLED_DONE = "Your registration has been cancelled and your saved answers removed. Message us any time to start again."
NOT_NOW = "No problem! Message us whenever you're ready to register."
OPTED_OUT = "You have been unsubscribed and won't receive more messages from Ezina. Send START any time to rejoin."
OPTED_IN = "Welcome back! You'll receive messages from Ezina again."
HANDOFF = "I'm passing you to a member of the Ezina team. They will contact you here soon."
RATE_LIMITED = "You are sending messages very quickly. Please wait a moment and try again."
GENERIC_ERROR = "Sorry, something went wrong on our side. Please send your message again in a moment."
REGISTER_FIRST = "To do that, please register first. Would you like to register your farm now? It's free."
NOT_YET = "That feature is coming soon. For now I can help you with your registration and its status."
FINISH_FIRST = "Let's finish your registration first, then we can do that."


def welcome_back(name: str | None) -> str:
    return f"Welcome back{', ' + name.split()[0] if name else ''}! Let's continue your registration."


def status_text(registration_status: str, verification_status: str, kind: str) -> str:
    reg = {
        "NOT_STARTED": "You have not started registering yet.",
        "IN_PROGRESS": "Your registration is in progress and not yet submitted.",
        "SUBMITTED": "Your registration has been submitted.",
        "CANCELLED": "Your registration was cancelled.",
    }.get(registration_status, "I could not find your registration.")
    ver = {
        VerificationStatus.NOT_SUBMITTED: "",
        VerificationStatus.PENDING: "Verification is pending. Our team will contact you when it is done.",
        VerificationStatus.VERIFIED: "Your farm has been verified by the Ezina team. ✅",
        VerificationStatus.REJECTED: "Your verification was not approved. Our team will contact you with details.",
        VerificationStatus.NEEDS_MORE_INFO: "Our team needs a little more information from you. They will contact you.",
    }.get(VerificationStatus(verification_status), "")
    if kind == "registration":
        return reg
    return ver or "Verification has not started yet because registration is not submitted."


def verification_notification(status: str, notes: str | None) -> str:
    base = {
        "VERIFIED": "Good news! Your Ezina farmer registration has been verified. ✅",
        "REJECTED": "Your Ezina verification was not approved.",
        "NEEDS_MORE_INFO": "The Ezina team needs a little more information to complete your verification.",
    }[status]
    return f"{base} {notes}".strip() if notes else base
