"""Optional LLM fallback (LLM_FALLBACK_ENABLED=false by default): used only when every earlier strategy failed.

Only the OCR lines and the doc_type are sent to the Claude API, with every digit masked as "#" (a name has none), and the
reply is forced through one tool with a JSON schema. The reply is then checked with the same name rules as every other
strategy, and every word of the returned name must really appear in the OCR text (a name the model made up is rejected).
"""
from __future__ import annotations

import logging
import re
from typing import Any

from ezina_id_verify.config import Settings
from ezina_id_verify.name.ocr import OcrLine
from ezina_id_verify.name.rules import Candidate, StopWords, clean_name, collapse, is_name_like, join_name

log = logging.getLogger("ezina_id_verify.llm")

MAX_LINES = 60
MAX_LINE_CHARS = 120

TOOL = {
    "name": "record_name",
    "description": "Record the cardholder's own name read from the OCR lines of an ID document.",
    "input_schema": {
        "type": "object",
        "properties": {
            "found": {"type": "boolean", "description": "true only if the cardholder's own name is clearly present"},
            "given_names": {"type": ["string", "null"]},
            "surname": {"type": ["string", "null"]},
            "full_name": {"type": ["string", "null"]},
        },
        "required": ["found"],
    },
}

SYSTEM = (
    "You read the cardholder's own name from the OCR text lines of an ID document. "
    "Return only the cardholder's own name. Never return a father's, husband's, mother's or any other relative's name. "
    "Never return numbers, dates, places, headers or labels. If you are not sure, set found to false. "
    "Always answer by calling the record_name tool."
)


class LlmUnavailable(Exception):
    """The fallback is enabled but cannot be used (not configured, or the API failed)."""


_client: Any = None


def set_client(client: Any | None) -> None:
    """Use this client (anything with an async `messages.create`) instead of the Anthropic SDK. Mainly for tests."""
    global _client
    _client = client


def _get_client(settings: Settings) -> Any:
    if _client is not None:
        return _client
    key = settings.anthropic_api_key.get_secret_value()
    if not key or not settings.claude_model:
        raise LlmUnavailable("ANTHROPIC_API_KEY and CLAUDE_MODEL must be set for the LLM fallback")
    try:
        from anthropic import AsyncAnthropic
    except ImportError as e:  # pragma: no cover - depends on the install
        raise LlmUnavailable("the anthropic package is not installed (pip install ezina-id-verify[llm])") from e
    return AsyncAnthropic(api_key=key, timeout=20.0, max_retries=1)


def masked_lines(lines: list[OcrLine]) -> list[str]:
    return [re.sub(r"\d", "#", l.text)[:MAX_LINE_CHARS] for l in lines[:MAX_LINES]]


def _tool_input(response: Any) -> dict | None:
    for block in getattr(response, "content", None) or []:
        if getattr(block, "type", None) == "tool_use" and isinstance(getattr(block, "input", None), dict):
            return block.input
    return None


def validate_reply(reply: dict, lines: list[OcrLine], stop: StopWords) -> Candidate | None:
    """Apply the name rules to the model's answer; None if anything fails."""
    if reply.get("found") is not True:
        return None
    given = clean_name(str(reply.get("given_names") or ""), stop.titles) or None
    surname = clean_name(str(reply.get("surname") or ""), stop.titles) or None
    full = clean_name(str(reply.get("full_name") or ""), stop.titles) or None
    if given or surname:
        full = join_name(given, surname)
    elif not full:
        return None
    parts = [p for p in (given, surname) if p] or [full]
    if not all(is_name_like(p, stop, check_tokens=False) for p in [*parts, full]):
        return None
    seen = {w for l in lines for w in re.findall(r"[^\W\d_]+", l.text.lower())}
    if any(w not in seen for w in re.findall(r"[^\W\d_]+", full.lower())):
        return None  # a word that is not on the document: made up
    return Candidate("llm", full, given_names=given, surname=surname)


async def extract_llm_name(doc_type: str, lines: list[OcrLine], settings: Settings, stop: StopWords) -> Candidate | None:
    """Ask the model. Raises LlmUnavailable when it cannot be used; returns None when it finds no valid name."""
    client = _get_client(settings)
    numbered = "\n".join(f"{i}. {text}" for i, text in enumerate(masked_lines(lines), 1))
    try:
        response = await client.messages.create(
            model=settings.claude_model or "unset", max_tokens=300, system=SYSTEM,
            messages=[{"role": "user", "content": f"Document type: {doc_type}\nOCR lines (digits are masked as #):\n{numbered}"}],
            tools=[TOOL], tool_choice={"type": "tool", "name": "record_name"},
        )
    except Exception as e:  # network, auth, rate limit ...: never include the request or the response
        log.warning("llm fallback failed", extra={"error": type(e).__name__})
        raise LlmUnavailable(type(e).__name__) from e
    reply = _tool_input(response)
    return validate_reply(reply, lines, stop) if reply is not None else None
