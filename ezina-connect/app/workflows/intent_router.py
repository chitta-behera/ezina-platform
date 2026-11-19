"""Maps (intent, flow situation) -> a deterministic Action. Pure function; easy to unit test."""
from __future__ import annotations

from enum import StrEnum

from app.enums import Intent


class Action(StrEnum):
    ANSWER = "ANSWER"  # treat message as an answer / correction in the active flow
    CONFIRM = "CONFIRM"
    DENY = "DENY"
    CANCEL = "CANCEL"
    OPT_OUT = "OPT_OUT"
    HANDOFF = "HANDOFF"
    STATUS_REGISTRATION = "STATUS_REGISTRATION"
    STATUS_VERIFICATION = "STATUS_VERIFICATION"
    GREET_RESUME = "GREET_RESUME"  # greeting while a flow is active -> welcome back + continue
    START_REGISTRATION = "START_REGISTRATION"
    FINISH_FIRST = "FINISH_FIRST"  # other intent mid-registration: finish registration first
    REGISTER_FIRST = "REGISTER_FIRST"  # unregistered farmer asking for farm/crop/harvest actions
    NOT_YET = "NOT_YET"  # registered farmer, feature not available yet
    GENERAL = "GENERAL"  # answer briefly (Claude, guarded) and re-ask the current question
    GREET_REGISTERED = "GREET_REGISTERED"


_LATER_FEATURES = {
    Intent.ADD_FARM,
    Intent.ADD_CROP,
    Intent.UPDATE_CROP,
    Intent.UPDATE_PROFILE,
    Intent.SHARE_HARVEST_AVAILABILITY,
}


def route(intent: Intent, *, registered: bool, in_registration: bool, has_data: bool) -> Action:
    # Always honoured, in any state.
    if intent == Intent.OPT_OUT:
        return Action.OPT_OUT
    if intent == Intent.REQUEST_HUMAN_SUPPORT:
        return Action.HANDOFF
    if intent == Intent.CHECK_REGISTRATION_STATUS:
        return Action.STATUS_REGISTRATION
    if intent == Intent.CHECK_VERIFICATION_STATUS:
        return Action.STATUS_VERIFICATION

    if in_registration:
        if intent == Intent.CANCEL_REGISTRATION:
            return Action.CANCEL
        if intent == Intent.CONFIRM:
            return Action.CONFIRM
        if intent == Intent.DENY:
            return Action.DENY
        if intent in (Intent.PROVIDE_INFORMATION, Intent.CORRECT_INFORMATION):
            return Action.ANSWER
        if intent in (Intent.GREETING, Intent.REGISTER_FARMER):
            return Action.ANSWER if has_data else Action.GREET_RESUME
        if intent in _LATER_FEATURES:
            return Action.ANSWER if has_data else Action.FINISH_FIRST
        # GENERAL_QUESTION / UNKNOWN: prefer reading it as an answer if it carries data
        return Action.ANSWER if has_data else Action.GENERAL

    if registered:
        if intent == Intent.GREETING:
            return Action.GREET_REGISTERED
        if intent in _LATER_FEATURES:
            return Action.NOT_YET
        return Action.GENERAL

    # not registered, no active flow
    if intent in (Intent.REGISTER_FARMER, Intent.GREETING, Intent.CONFIRM, Intent.PROVIDE_INFORMATION):
        return Action.START_REGISTRATION
    if intent in _LATER_FEATURES:
        return Action.REGISTER_FIRST
    return Action.GENERAL
