"""Deterministic (templated) farmer-facing messages. Used as the safe fallback for Claude replies,
and always for legal / data-accuracy messages (consent, review summary, statuses)."""
from __future__ import annotations

from app.config import Settings
from app.enums import Stage, VerificationStatus
from app.schemas.conversation import Button, Draft, ListRow, Reply
from app.workflows import address_flow, identity_flow
from app.workflows.validators import UNIT_LABEL, country_name

# ids of interactive replies handled deterministically by Python
BTN_CONSENT_YES, BTN_CONSENT_NO = "consent_agree", "consent_no"
BTN_LOC_SKIP = "loc_skip"
BTN_FARMPHOTO_SKIP = "farmphoto_skip"
BTN_CROPPHOTO_SKIP = "cropphoto_skip"
BTN_REVIEW_CONFIRM, BTN_REVIEW_EDIT, BTN_REVIEW_CANCEL = "review_confirm", "review_edit", "review_cancel"
BTN_YES, BTN_NO = "confirm_yes", "confirm_no"
BTN_CANCEL_YES, BTN_CANCEL_NO = "cancel_yes", "cancel_no"
BTN_ID_LATER, BTN_SELFIE_LATER, BTN_ID_CHANGE = "id_later", "selfie_later", "id_change"
BTN_NAME_CHANGE, BTN_ID_REUPLOAD = "name_change", "id_reupload"  # name check: mismatch choices
BTN_SELFIE_NEW = "selfie_new"  # face check mismatch: [Take a new selfie] (the other choice is BTN_ID_REUPLOAD)
BTN_IDENTITY_START = "identity_start"
IDTYPE_PREFIX, IDTYPE_NONE = "idtype_", "idtype_none"
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
            "so buyers can find you. To verify you, we'll also ask for a photo of your ID card and a selfie. "
            "These are kept private and used only for verification. Do you agree?"
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
        return address_prompt(draft)
    if stage == Stage.COLLECT_CROPS:
        return Reply("What crops do you grow at the moment?")
    if stage == Stage.COLLECT_CULTIVATION_AREA:
        return Reply("About how much land do you use for farming? For example: *5 acres* or *2 hectares*.")
    if stage == Stage.COLLECT_GPS_LOCATION:
        return location_prompt()
    if stage == Stage.COLLECT_ID_DOCUMENT:
        return id_prompt(draft, settings)
    if stage == Stage.COLLECT_SELFIE:
        return selfie_prompt(draft)
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


def address_question(country: str | None) -> str:
    """The first address question: wording, a short instruction and an example for the farmer's country."""
    fmt = address_flow.format_for(country)
    return "\n".join(["What is the full address of your farm?", fmt.instruction, f"For example: _{fmt.example}_"])


def address_followup(missing: list[str]) -> str:
    return f"Thanks! What is the *{address_flow.join_parts(missing)}* of your farm? Please send only that part."


def address_prompt(draft: Draft) -> Reply:
    """Ask for the address, or (after an incomplete answer) only for the parts that are still missing."""
    if draft.address_missing:
        return Reply(address_followup(draft.address_missing))
    return Reply(address_question(draft.country))


ID_RECEIVED = "Thank you, your ID has been received ✅."
NAME_CHECK_HOLD = "Thank you! Checking your ID, this takes a few seconds…"
NAME_NOT_FOUND = (
    "I couldn't read the name on that photo. Please take a clearer photo of the ID: lay it flat in good light "
    "with all 4 corners showing."
)
ID_SEND_PHOTO = "Please send a photo of your ID: tap 📎 (Attach) → Camera or Gallery."
NAME_CHECK_GIVE_UP = "Thank you. The Ezina team will review your ID and contact you if anything more is needed."
NAME_ASK = "Please type your full name exactly as it is written on your ID."
NAME_INVALID = "Sorry, that doesn't look like a name. Please type your full name exactly as it is written on your ID."


def name_mismatch_reply(given_name: str | None) -> Reply:
    """The name on the ID does not match what the farmer gave. Shows only the name the farmer gave, never the ID's."""
    who = f" ({given_name})" if given_name else ""
    return Reply(
        body=f"The name on your ID doesn't match the name you gave us{who}. Please choose an option:",
        buttons=[Button(BTN_NAME_CHANGE, "Change my name"), Button(BTN_ID_REUPLOAD, "Upload another ID")],
    )


def id_prompt(draft: Draft, settings: Settings) -> Reply:
    """ID type list (filtered by country), then the front / back photo request. Never asks for a number."""
    if draft.name_awaiting:
        return Reply(NAME_ASK)
    if draft.name_choice_pending:
        return name_mismatch_reply(draft.full_name)
    lang = draft.preferred_language
    if not draft.id_type:
        rows = [ListRow(f"{IDTYPE_PREFIX}{t.code}", t.name(lang)[:24]) for t in identity_flow.id_types(draft.country)]
        rows.append(ListRow(IDTYPE_NONE, "I don't have any", "I don't have any of these"))
        rows.append(ListRow(BTN_ID_LATER, "Send later"))
        return Reply(
            body="Now, to verify you, which ID card can you share? It is kept private and used only for verification.",
            list_rows=rows, list_button_label="Choose ID",
        )
    t = identity_flow.find_type(draft.country, draft.id_type)
    name = t.name(lang) if t else "ID"
    side = "back" if draft.id_front_doc else "front"
    lines = [
        f"Please send a clear photo of the *{side}* of your {name}: tap 📎 (Attach) → Camera or Gallery. "
        "Put it on a flat surface in good light, with all 4 corners showing."
    ]
    if t and t.mask and side == "front":
        lines.append("Before you take the photo, please *cover the first 8 digits* of the number.")
    lines.append("Please don't type the ID number, I only need the photo.")
    return Reply(
        body="\n".join(lines),
        buttons=[Button(BTN_ID_LATER, "Send later"), Button(BTN_ID_CHANGE, "Change ID type")],
    )


SELFIE_RECEIVED = "Thank you, your selfie has been received ✅."
FACE_CHECK_HOLD = "Thank you! Checking your selfie, this takes a few seconds…"
FACE_CHECK_PENDING = (
    "We couldn't finish the automatic photo check right now. Your selfie is saved, and the Ezina team will complete "
    "the check. You don't need to do anything."
)
SELFIE_TIPS = (
    "Tips for the new selfie: face the light, no cap or sunglasses, keep your face fully in the frame, and look "
    "the way you do on your ID if you can."
)
FACE_NEW_SELFIE = (
    "I couldn't see your face clearly in that selfie. Please take a new selfie now with your front camera, "
    "with your face clearly visible."
)
FACE_ID_UNCLEAR = (
    "The photo on your ID isn't clear enough for me. Please send a clearer photo of the front of your ID "
    "(or a different ID)."
)
FACE_CHECK_GIVE_UP = "Thank you. The Ezina team will review your photos and contact you if anything more is needed."


# One specific tip for the retry message, chosen from the selfie quality warnings (first match in this order wins).
# The farmer is never told a score or a threshold.
_FACE_TIPS = (
    ("eyes_closed", "Keep your eyes open and look at the camera."),
    ("sunglasses", "Please take off your sunglasses."),
    ("selfie_dark", "Face the light so your face is not in the shadow."),
    ("selfie_blurry", "Hold the phone steady so the photo is sharp."),
    ("multiple_faces_selfie", "Make sure only your face is in the photo."),
)


def face_tip(warnings: list[str] | None) -> str | None:
    """The one retry tip for these selfie quality warnings, or None."""
    have = set(warnings or [])
    return next((tip for code, tip in _FACE_TIPS if code in have), None)


def face_mismatch_reply(tip: str | None = None) -> Reply:
    """The selfie does not seem to match the photo on the ID. No score, no accusation; two buttons."""
    extra = f"\n\n{tip}" if tip else ""
    return Reply(
        body=f"Your selfie doesn't seem to match the photo on your ID. Please choose an option:\n\n{SELFIE_TIPS}{extra}",
        buttons=[Button(BTN_SELFIE_NEW, "Take a new selfie"), Button(BTN_ID_REUPLOAD, "Upload another ID")],
    )


def selfie_prompt(draft: Draft) -> Reply:
    if draft.face_choice_pending:
        return face_mismatch_reply()
    challenge = f" and {identity_flow.challenge_text(draft.selfie_challenge)}" if draft.selfie_challenge else ""
    return Reply(
        body=(
            "Last step for verification: please send a *new selfie*: tap 📎 (Attach) → Camera and take it now "
            f"with your front camera{challenge}. "
            "Show your face clearly (no sunglasses or cap). It is kept private and used only for verification."
        ),
        buttons=[Button(BTN_SELFIE_LATER, "Send later")],
    )


def _received(flag: bool) -> str:
    return "received ✅" if flag else "pending"


def review_reply(draft: Draft) -> Reply:
    lines = ["Here is your registration summary:"]
    lines.append(f"*Name:* {draft.full_name}")
    lines.append(f"*Country:* {country_name(draft.country)}")
    lines.append(f"*Address:* {draft.full_address_text}")
    if draft.farm_name:
        lines.append(f"*Farm name:* {draft.farm_name}")
    lines.append(f"*Crops:* {_crops_display(draft.crops)}")
    lines.append(f"*Land:* {area_display(draft)}")
    lines.append("*Location:* received ✅" if draft.has_location else "*Location:* not shared yet")
    lines.append(f"*ID document:* {_received(draft.id_received)}")
    lines.append(f"*Selfie:* {_received(draft.selfie_received)}")
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
    return Reply("Sure! What would you like to change? For example: _change land to 4 hectares_. (Your ID, selfie and photos can't be changed.)")


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
        "full_address_text": "the address",
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


def submitted_reply(id_received: bool, selfie_received: bool) -> Reply:
    """After confirmation. Verification only starts once both the ID document and the selfie are received."""
    if id_received and selfie_received:
        return Reply(REGISTERED_SUBMITTED)
    missing = " and ".join(x for x, ok in (("ID document photo", id_received), ("selfie", selfie_received)) if not ok)
    return Reply(
        "Thank you for registering with Ezina. Your farmer registration has been submitted. "
        f"To start verification we still need your {missing}. Verification starts once we receive it. "
        "Tap *Send now* whenever you are ready.",
        buttons=[Button(BTN_IDENTITY_START, "Send now")],
    )


IDENTITY_COMPLETE = (
    "Thank you! We have everything we need. Your registration is now pending verification. "
    "Our team will contact you once the verification process is complete."
)
IDENTITY_PARTIAL = "Thank you! Verification will start once we receive the remaining item."
IDENTITY_ALREADY = "We already have your ID document and selfie. Our team will contact you about verification."
ID_NUMBER_REFUSED = "For your safety please don't type ID numbers. I only need a photo of the ID card."
ID_FIRST_CHOOSE_TYPE = "First, please choose which ID card you want to send."
SELFIE_NOT_FILE = "For the selfie I need a live photo from your front camera, not a file."
ID_DEFERRED = "No problem, you can send it later. Just message us when you are ready."
ID_NEEDS_HELP = "Thank you. That is okay, someone from the Ezina team will help you with this step."
SELFIE_NEW_CHALLENGE = "That took a little long, so here is a new challenge."

CANCELLED_DONE = "Your registration has been cancelled and your saved answers removed. Message us any time to start again."
NOT_NOW = "No problem! Message us whenever you're ready to register."
OPTED_OUT = "You have been unsubscribed and won't receive more messages from Ezina. Send START any time to rejoin."
OPTED_IN = "Welcome back! You'll receive messages from Ezina again."
HANDOFF = "I'm passing you to a member of the Ezina team. They will contact you here soon."
RATE_LIMITED = "You are sending messages very quickly. Please wait a moment and try again."
GENERIC_ERROR = "Sorry, something went wrong on our side. Please send your message again in a moment."
REVIEW_NO_MEDIA_EDIT = (
    "Your ID document, selfie and photos can't be changed here. You can edit your other details "
    "(name, country, farm name, address, crops, land size, language) or tap Confirm."
)
REVIEW_COUNTRY_LOCKED = (
    "The country can't be changed here because it no longer matches your ID document. "
    "You can edit your other details or tap Confirm."
)
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
