"""Object storage: filesystem (dev/tests) / S3-compatible (prod) backends.

Keys follow the layout `<area>/<space_id>/<asset_id>/<name>` where area is
`originals` (immutable) or `derivatives` (regenerated). The API mints URLs;
browsers move bytes directly (ADR-004).
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Protocol

from app.config import Settings
from app.logging import get_logger

logger = get_logger(__name__)


class Storage(Protocol):
    async def presign_put(self, key: str, mime: str, max_bytes: int, ttl_seconds: int) -> str: ...
    async def presign_get(self, key: str, ttl_seconds: int) -> str: ...
    async def exists(self, key: str) -> bool: ...
    async def size(self, key: str) -> int | None: ...
    async def read_bytes(self, key: str) -> bytes: ...
    async def write_bytes(self, key: str, data: bytes, mime: str = "") -> None: ...
    async def delete(self, key: str) -> None: ...
    async def delete_prefix(self, prefix: str) -> int:
        """Delete every key under prefix. Returns the number removed."""
        ...


class FilesystemStorage:
    """Dev/test backend. Presigned URLs are local file URLs understood only
    by tests and dev tooling — never exposed as public links."""

    def __init__(self, root: str) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if ".." in Path(key).parts or Path(key).is_absolute():
            raise ValueError("invalid storage key")
        return self._root / key

    async def presign_put(self, key: str, mime: str, max_bytes: int, ttl_seconds: int) -> str:
        path = self._path(key)
        await asyncio.to_thread(path.parent.mkdir, True, True)
        return f"file://{path.resolve()}?expires={int(time.time()) + ttl_seconds}"

    async def presign_get(self, key: str, ttl_seconds: int) -> str:
        return f"file://{self._path(key).resolve()}?expires={int(time.time()) + ttl_seconds}"

    async def exists(self, key: str) -> bool:
        return await asyncio.to_thread(self._path(key).exists)

    async def size(self, key: str) -> int | None:
        path = self._path(key)
        exists = await asyncio.to_thread(path.exists)
        if not exists:
            return None
        stat = await asyncio.to_thread(path.stat)
        return stat.st_size

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._path(key).unlink, True)

    async def delete_prefix(self, prefix: str) -> int:
        base = self._path(prefix.rstrip("/") or ".")
        removed = 0

        def _run() -> int:
            count = 0
            if base.is_dir():
                for path in sorted(base.rglob("*")):
                    if path.is_file():
                        path.unlink()
                        count += 1
            elif base.is_file():
                base.unlink()
                count = 1
            return count

        removed = await asyncio.to_thread(_run)
        return removed

    async def read_bytes(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)

    async def write_bytes(self, key: str, data: bytes, mime: str = "") -> None:
        path = self._path(key)

        def _run() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        await asyncio.to_thread(_run)

    # Backwards-compatible alias used by tests (uploader simulation).
    async def put_bytes(self, key: str, data: bytes) -> None:
        await self.write_bytes(key, data)


class S3Storage:
    """S3-compatible backend (MinIO in compose, managed vendor in prod)."""

    def __init__(self, settings: Settings) -> None:
        import boto3  # lazy: keeps the import graph light for dev/test
        from botocore.config import Config

        self._settings = settings
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url or None,
            aws_access_key_id=settings.s3_access_key or None,
            aws_secret_access_key=settings.s3_secret_key or None,
            region_name=settings.s3_region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def _bucket_for(self, key: str) -> str:
        if key.startswith("originals/"):
            return self._settings.s3_bucket_originals
        return self._settings.s3_bucket_derivatives

    async def presign_put(self, key: str, mime: str, max_bytes: int, ttl_seconds: int) -> str:
        return await asyncio.to_thread(
            self._client.generate_presigned_url,
            "put_object",
            Params={"Bucket": self._bucket_for(key), "Key": key, "ContentType": mime},
            ExpiresIn=ttl_seconds,
        )

    async def presign_get(self, key: str, ttl_seconds: int) -> str:
        return await asyncio.to_thread(
            self._client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self._bucket_for(key), "Key": key},
            ExpiresIn=ttl_seconds,
        )

    async def exists(self, key: str) -> bool:
        return (await self.size(key)) is not None

    async def size(self, key: str) -> int | None:
        try:
            head = await asyncio.to_thread(
                self._client.head_object, Bucket=self._bucket_for(key), Key=key
            )
        except Exception as exc:
            if "404" in str(exc) or "Not Found" in str(exc):
                return None
            raise
        content_length = head.get("ContentLength")
        return int(content_length) if content_length is not None else None

    async def read_bytes(self, key: str) -> bytes:
        response = await asyncio.to_thread(
            self._client.get_object, Bucket=self._bucket_for(key), Key=key
        )
        body = response["Body"]
        try:
            return await asyncio.to_thread(body.read)
        finally:
            body.close()

    async def write_bytes(self, key: str, data: bytes, mime: str = "") -> None:
        kwargs: dict = {"Bucket": self._bucket_for(key), "Key": key, "Body": data}
        if mime:
            kwargs["ContentType"] = mime
        await asyncio.to_thread(self._client.put_object, **kwargs)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(
            self._client.delete_object, Bucket=self._bucket_for(key), Key=key
        )

    async def delete_prefix(self, prefix: str) -> int:
        bucket = self._bucket_for(prefix)
        removed = 0
        token: str | None = None
        while True:
            kwargs: dict = {"Bucket": bucket, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            page = await asyncio.to_thread(self._client.list_objects_v2, **kwargs)
            contents = page.get("Contents", [])
            if contents:
                await asyncio.to_thread(
                    self._client.delete_objects,
                    Bucket=bucket,
                    Delete={"Objects": [{"Key": o["Key"]} for o in contents]},
                )
                removed += len(contents)
            token = page.get("NextContinuationToken")
            if not token:
                break
        return removed


_storage: Storage | None = None


def get_storage(settings: Settings | None = None) -> Storage:
    global _storage
    if _storage is not None:
        return _storage
    from app.config import get_settings

    resolved = settings or get_settings()
    if resolved.storage_driver == "s3":
        _storage = S3Storage(resolved)
    else:
        _storage = FilesystemStorage(os.path.join(resolved.storage_dir))
    return _storage


def reset_storage() -> None:
    global _storage
    _storage = None
