"""ClaudeService: interprets farmer messages and drafts replies via ONE forced tool call.

Claude has no write tools. The tool exists only to obtain a guaranteed JSON shape (AIResponse).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import anthropic
from pydantic import ValidationError

from app.config import Settings
from app.schemas.ai_response import AIResponse, tool_input_schema

log = logging.getLogger("ezina.claude")
PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "farmer_assistant.txt"
TOOL_NAME = "record_interpretation"
MAX_FARMER_CHARS = 1500


@dataclass
class ClaudeContext:
    stage: str
    next_field: str | None  # what Python wants collected at this stage
    reply_target: str | None  # topic the reply must lead to if the answer is accepted
    collected: dict[str, Any]
    history: list[tuple[str, str]]  # (role "farmer"|"ezina", text), oldest first
    message_text: str
    now: datetime
    current_topic: str | None = None  # topic of the open question (for clarifications)
    preferred_language: str | None = None
    mode: str = "interpret"  # interpret | compose
    saved_summary: dict[str, Any] = field(default_factory=dict)  # compose mode: what was just saved
    address: dict[str, Any] | None = None  # address step: the country's instruction, example, expected parts


def load_system_prompt(settings: Settings) -> str:
    text = PROMPT_PATH.read_text(encoding="utf-8")
    langs = ", ".join(f"{c} ({n})" for c, n in settings.supported_languages.items())
    return text.replace("{{assistant_name}}", "Ezina Assistant").replace("{{supported_languages}}", langs)


def _clean(text: str) -> str:
    # keep farmer text from forging our prompt tags
    return text.replace("<", "‹").replace(">", "›")[:MAX_FARMER_CHARS]


def build_user_message(ctx: ClaudeContext) -> str:
    history = "\n".join(f"{role}: {_clean(t)[:400]}" for role, t in ctx.history) or "(none)"
    state = {
        "current_stage": ctx.stage,
        "next_field_python_wants": ctx.next_field,
        "already_collected": ctx.collected,
        "preferred_language": ctx.preferred_language,
    }
    if ctx.address:
        state["address_format"] = ctx.address
    if ctx.mode == "compose":
        target = (
            "COMPOSE ONLY. The program already handled the farmer's message and saved: "
            f"{json.dumps(ctx.saved_summary, ensure_ascii=False)}. Do not extract anything (leave extracted_data empty, "
            "intent PROVIDE_INFORMATION). Write suggested_response: a brief natural acknowledgement, then ask ONLY "
            f"about: {ctx.reply_target}."
        )
    else:
        target = (
            "Interpret the message. If the farmer's answer is accepted, write suggested_response as a brief "
            f"acknowledgement, then ask ONLY about: {ctx.reply_target}. If the answer is unclear, wrong or "
            "implausible, set requires_clarification=true and make suggested_response one simple clarifying question "
            f"about the CURRENT topic: {ctx.current_topic}. If the message is not an answer (question, greeting, "
            "complaint), respond briefly and then ask the current question again."
        )
    return (
        f"<now>{ctx.now.isoformat(timespec='minutes')}</now>\n"
        f"<state>\n{json.dumps(state, ensure_ascii=False, default=str)}\n</state>\n"
        f"<reply_target>\n{target}\n</reply_target>\n"
        f"<recent_conversation>\n{history}\n</recent_conversation>\n"
        f"<farmer_message>\n{_clean(ctx.message_text)}\n</farmer_message>"
    )


class ClaudeService:
    def __init__(self, settings: Settings, client: anthropic.AsyncAnthropic | None = None):
        self.s = settings
        self.system_prompt = load_system_prompt(settings)
        self.client = client or anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key.get_secret_value() or "missing",
            max_retries=settings.claude_max_retries,  # exponential backoff on 429 / 5xx / overloaded
            timeout=settings.claude_timeout_seconds,
        )
        self._force_tool = True
        self.tool = {
            "name": TOOL_NAME,
            "description": "Report your interpretation of the farmer's message and the reply to send.",
            "input_schema": tool_input_schema(),
        }

    async def interpret(self, ctx: ClaudeContext) -> AIResponse | None:
        """Return a validated AIResponse, or None if Claude is unavailable / keeps returning bad output."""
        user_text = build_user_message(ctx)
        attempt = 0
        while attempt < 2:
            attempt += 1
            try:
                resp = await self.client.messages.create(
                    model=self.s.claude_model,
                    max_tokens=self.s.claude_max_tokens,
                    system=[{"type": "text", "text": self.system_prompt, "cache_control": {"type": "ephemeral"}}],
                    tools=[self.tool],
                    # Some models reject a forced tool_choice; we then fall back to "auto" (the prompt requires the tool).
                    tool_choice={"type": "tool", "name": TOOL_NAME} if self._force_tool else {"type": "auto"},
                    messages=[{"role": "user", "content": user_text}],
                )
            except anthropic.BadRequestError as e:
                if self._force_tool and "tool_choice" in str(e):
                    log.warning("model does not support forced tool_choice; using auto", extra={"model": self.s.claude_model})
                    self._force_tool = False
                    attempt -= 1  # the switch itself doesn't use up a retry
                    continue
                log.error("claude call failed", extra={"status": 400, "detail": str(e)[:300], "model": self.s.claude_model})
                return None
            except anthropic.APIError as e:  # SDK already retried transient errors
                log.error(
                    "claude call failed",
                    extra={
                        "error_type": type(e).__name__,
                        "status": getattr(e, "status_code", None),
                        "detail": str(e)[:300],
                        "model": self.s.claude_model,
                    },
                )
                return None
            block = next((b for b in resp.content if getattr(b, "type", "") == "tool_use"), None)
            if block is None:
                log.warning("claude returned no tool_use", extra={"attempt": attempt})
                continue
            try:
                return AIResponse.model_validate(block.input)
            except ValidationError as e:
                log.warning("claude output failed validation", extra={"attempt": attempt, "errors": e.error_count()})
        return None
