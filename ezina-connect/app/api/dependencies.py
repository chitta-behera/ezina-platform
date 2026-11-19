"""FastAPI dependencies: container, DB session, admin API-key auth."""
from __future__ import annotations

import hmac
from collections.abc import AsyncIterator

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.container import Container
from app.services.message_processor import MessageProcessor


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_processor(request: Request) -> MessageProcessor:
    return request.app.state.processor


async def get_session(c: Container = Depends(get_container)) -> AsyncIterator[AsyncSession]:
    async with c.db.sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def require_admin(
    x_api_key: str | None = Header(default=None), c: Container = Depends(get_container)
) -> None:
    expected = c.settings.admin_api_key.get_secret_value()
    # Fail closed: with no key configured, the admin surface is disabled entirely.
    if not expected:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "admin API disabled: ADMIN_API_KEY not set")
    if not x_api_key or not hmac.compare_digest(x_api_key.encode(), expected.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid API key")
