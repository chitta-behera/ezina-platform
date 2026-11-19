"""FastAPI application factory."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api import admin, webhook, whatsapp
from app.config import get_settings
from app.logging_config import setup_logging
from app.services.container import Container
from app.services.message_processor import MessageProcessor

log = logging.getLogger("ezina.app")


def create_app(container: Container | None = None) -> FastAPI:
    """`container` can be injected (tests); otherwise it is built from settings on startup."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        owned = container is None
        c = container or Container.build(get_settings())
        if owned:
            setup_logging(c.settings.log_level, c.settings.is_production)
        app.state.container = c
        app.state.processor = MessageProcessor(c)
        await app.state.processor.recover()  # don't lose messages across restarts
        yield
        await app.state.processor.drain()
        if owned:
            await c.aclose()

    app = FastAPI(title="Ezina Connect", version="0.1.0", lifespan=lifespan)
    if container is not None:  # allow use without running lifespan (ASGITransport in tests)
        app.state.container = container
        app.state.processor = MessageProcessor(container)

    app.include_router(webhook.router)
    app.include_router(whatsapp.router)
    app.include_router(admin.router)

    @app.get("/health")
    async def health():
        c: Container = app.state.container
        try:
            await c.db.ping()
            return {"status": "ok", "database": "ok"}
        except Exception:
            log.exception("health check: database unreachable")
            return JSONResponse({"status": "degraded", "database": "unreachable"}, status_code=503)

    return app


app = create_app()
