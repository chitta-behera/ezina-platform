"""Notifies the Ezina operations team (log + optional webhook) when a farmer needs a human."""
from __future__ import annotations

import logging

import httpx

from app.logging_config import mask_phone

log = logging.getLogger("ezina.ops")


class OpsNotifier:
    def __init__(self, webhook_url: str = "", client: httpx.AsyncClient | None = None):
        self.url = webhook_url
        self.client = client

    async def handoff(self, wa_id: str, reason: str) -> None:
        log.warning("HUMAN HANDOFF requested", extra={"farmer": mask_phone(wa_id), "reason": reason[:200]})
        if not self.url:
            return
        try:
            client = self.client or httpx.AsyncClient(timeout=10)
            try:
                await client.post(self.url, json={"event": "human_handoff", "farmer": mask_phone(wa_id), "reason": reason})
            finally:
                if self.client is None:
                    await client.aclose()
        except Exception as e:  # never break the conversation because ops webhook is down
            log.error("ops webhook failed", extra={"error": str(e)[:200]})
