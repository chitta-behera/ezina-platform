"""Object storage adapters: local filesystem (development) and S3-compatible (production)."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Protocol

from app.config import Settings


class StorageBackend(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> str: ...
    async def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents:
            raise ValueError("invalid storage key")
        return p

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        p = self._path(key)

        def _write() -> None:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)

        await asyncio.to_thread(_write)
        return key

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(lambda: self._path(key).unlink(missing_ok=True))


class S3Storage:
    def __init__(self, settings: Settings):
        import boto3  # imported lazily so local development does not need S3 config

        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url or None,
            aws_access_key_id=settings.s3_access_key_id or None,
            aws_secret_access_key=settings.s3_secret_access_key.get_secret_value() or None,
        )

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        await asyncio.to_thread(
            self.client.put_object, Bucket=self.bucket, Key=key, Body=data, ContentType=content_type
        )
        return key

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=key)


def get_storage(settings: Settings) -> StorageBackend:
    if settings.media_storage_backend.lower() == "s3":
        if not settings.s3_bucket:
            raise RuntimeError("S3_BUCKET must be set when MEDIA_STORAGE_BACKEND=s3")
        return S3Storage(settings)
    return LocalStorage(settings.media_local_dir)
