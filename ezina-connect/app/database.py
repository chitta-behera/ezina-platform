"""Async SQLAlchemy engine/session management and declarative base + mixins."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import JSON, DateTime, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JSONType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(UTC)


def aware(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; normalise to UTC-aware."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


class Base(DeclarativeBase):
    pass


class UUIDPk:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, server_default=func.now(), nullable=False
    )


def normalize_database_url(url: str) -> tuple[str, dict]:
    """Accept Neon/Supabase style URLs and make them asyncpg-friendly."""
    connect_args: dict = {}
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    if url.startswith("postgresql+asyncpg://"):
        parsed = urlparse(url)
        query = dict(parse_qsl(parsed.query))
        sslmode = query.pop("sslmode", None)
        query.pop("channel_binding", None)
        if sslmode and sslmode != "disable":
            connect_args["ssl"] = True
        # Required behind PgBouncer transaction pooling (Neon / Supabase pooled URLs).
        connect_args["statement_cache_size"] = 0
        url = urlunparse(parsed._replace(query=urlencode(query)))
    return url, connect_args


class Database:
    def __init__(self, url: str):
        resolved, connect_args = normalize_database_url(url)
        self.is_postgres = resolved.startswith("postgresql")
        kwargs: dict = {"connect_args": connect_args}
        if self.is_postgres:
            kwargs.update(pool_size=10, max_overflow=10, pool_pre_ping=True)
        self.engine: AsyncEngine = create_async_engine(resolved, **kwargs)
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)

    async def dispose(self) -> None:
        await self.engine.dispose()

    async def ping(self) -> bool:
        async with self.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True


async def advisory_xact_lock(session: AsyncSession, key: str) -> None:
    """Per-key transaction-scoped lock on PostgreSQL (no-op elsewhere).

    The xact variant is used so it also works behind PgBouncer transaction pooling.
    """
    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": key})
