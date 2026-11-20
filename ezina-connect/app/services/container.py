"""Wires long-lived services together (no DI framework needed)."""
from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.database import Database
from app.services.claude_service import ClaudeService
from app.services.identity_service import IdentityService
from app.services.media_service import MediaService
from app.services.ops_notifier import OpsNotifier
from app.services.rate_limiter import RateLimiter
from app.services.storage_service import StorageBackend, get_identity_storage, get_storage
from app.services.whatsapp_service import WhatsAppService


@dataclass
class Container:
    settings: Settings
    db: Database
    claude: ClaudeService
    whatsapp: WhatsAppService
    media: MediaService
    storage: StorageBackend
    limiter: RateLimiter
    ops: OpsNotifier
    identity: IdentityService | None = None  # built from settings when not supplied (private identity storage)

    def __post_init__(self) -> None:
        if self.identity is None:
            self.identity = IdentityService(self.settings, self.whatsapp, get_identity_storage(self.settings))

    @classmethod
    def build(cls, settings: Settings) -> "Container":
        db = Database(settings.database_url)
        storage = get_storage(settings)
        wa = WhatsAppService(settings)
        return cls(
            settings=settings,
            db=db,
            claude=ClaudeService(settings),
            whatsapp=wa,
            media=MediaService(settings, wa, storage),
            storage=storage,
            limiter=RateLimiter(settings.rate_limit_per_minute),
            ops=OpsNotifier(settings.ops_webhook_url),
        )

    async def aclose(self) -> None:
        await self.whatsapp.aclose()
        await self.db.dispose()
