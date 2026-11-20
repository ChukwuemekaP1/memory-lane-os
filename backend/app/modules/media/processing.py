"""Media processing worker: probe, renditions, and metadata via FFmpeg.

Registered as the `process_media` background job (ARQ in prod, eager in
dev/tests). Originals are never modified; derivatives land under
`derivatives/<space>/<asset>/`. Failures mark the asset `failed` with a
user-safe reason and retry with backoff (3 attempts, then dead).
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

from app.errors import AppError
from app.logging import get_logger
from app.models.contributions import MediaAsset, MediaProcessingJob
from app.models.enums import JobStatus, MediaKind, MediaStatus
from app.services.ffmpeg import MediaToolError, run_ffmpeg, run_ffprobe_json
from app.services.jobs import job

logger = get_logger(__name__)

MAX_ATTEMPTS = 3


class ProcessingError(Exception):
    """User-safe processing failure (message is shown to uploaders)."""


async def _probe(path: Path) -> dict[str, Any]:
    try:
        out = await run_ffprobe_json(["-show_format", "-show_streams", str(path)])
    except MediaToolError as exc:
        raise ProcessingError(str(exc)) from None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        raise ProcessingError("Could not read this file.") from None


def _first_streams(probe: dict[str, Any]) -> tuple[dict | None, dict | None]:
    video = audio = None
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == "video" and video is None:
            video = stream
        elif stream.get("codec_type") == "audio" and audio is None:
            audio = stream
    return video, audio


async def _ffmpeg(args: list[str], label: str) -> None:
    try:
        await run_ffmpeg(args, label)
    except MediaToolError as exc:
        raise ProcessingError(str(exc)) from None


def _derivative_key(asset: MediaAsset, name: str) -> str:
    return f"derivatives/{asset.space_id}/{asset.id}/{name}"


async def _process_image(asset: MediaAsset, src: Path, workdir: Path) -> tuple[dict, list[dict]]:
    probe = await _probe(src)
    video, _ = _first_streams(probe)
    if video is None:
        raise ProcessingError("No image stream found.")
    width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    from app.services.storage import get_storage

    storage = get_storage()
    renditions = []
    for label, scale, quality in (("thumb", 320, 5), ("preview", 1280, 7)):
        out = workdir / f"{label}.jpg"
        await _ffmpeg(["-i", str(src), "-vf", f"scale={scale}:-2",
                       "-q:v", str(quality), str(out)], label)
        data = out.read_bytes()
        key = _derivative_key(asset, f"{label}.jpg")
        await storage.write_bytes(key, data, "image/jpeg")
        renditions.append({"label": label, "key": key, "mime": "image/jpeg",
                           "width": None, "height": None, "bytes": len(data)})
    return {"width": width, "height": height, "duration_ms": None}, renditions


async def _process_video(asset: MediaAsset, src: Path, workdir: Path) -> tuple[dict, list[dict]]:
    probe = await _probe(src)
    video, _ = _first_streams(probe)
    if video is None:
        raise ProcessingError("No video stream found.")
    width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    duration_ms = None
    try:
        duration_ms = int(float(probe.get("format", {}).get("duration", "0")) * 1000)
    except (TypeError, ValueError):
        pass
    from app.services.storage import get_storage

    storage = get_storage()
    renditions = []
    preview = workdir / "preview.mp4"
    await _ffmpeg(["-i", str(src), "-vf", "scale=1280:-2", "-c:v", "libx264",
                   "-preset", "veryfast", "-crf", "26", "-c:a", "aac", "-movflags",
                   "+faststart", str(preview)], "preview")
    data = preview.read_bytes()
    key = _derivative_key(asset, "preview.mp4")
    await storage.write_bytes(key, data, "video/mp4")
    renditions.append({"label": "preview", "key": key, "mime": "video/mp4",
                       "width": None, "height": None, "bytes": len(data)})
    poster = workdir / "poster.jpg"
    await _ffmpeg(["-ss", "1", "-i", str(src), "-frames:v", "1", "-q:v", "5", str(poster)],
                  "poster")
    data = poster.read_bytes()
    key = _derivative_key(asset, "poster.jpg")
    await storage.write_bytes(key, data, "image/jpeg")
    renditions.append({"label": "poster", "key": key, "mime": "image/jpeg",
                       "width": None, "height": None, "bytes": len(data)})
    return {"width": width, "height": height, "duration_ms": duration_ms}, renditions


async def _process_audio(asset: MediaAsset, src: Path, workdir: Path) -> tuple[dict, list[dict]]:
    probe = await _probe(src)
    _, audio = _first_streams(probe)
    if audio is None:
        raise ProcessingError("No audio stream found.")
    duration_ms = None
    try:
        duration_ms = int(float(probe.get("format", {}).get("duration", "0")) * 1000)
    except (TypeError, ValueError):
        pass
    from app.services.storage import get_storage

    storage = get_storage()
    normalized = workdir / "preview.m4a"
    await _ffmpeg(["-i", str(src), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                   "-c:a", "aac", str(normalized)], "preview")
    data = normalized.read_bytes()
    key = _derivative_key(asset, "preview.m4a")
    await storage.write_bytes(key, data, "audio/mp4")
    renditions = [{"label": "preview", "key": key, "mime": "audio/mp4",
                   "width": None, "height": None, "bytes": len(data)}]
    return {"width": None, "height": None, "duration_ms": duration_ms}, renditions


@job("process_media")
async def process_media_job(payload: dict[str, Any]) -> None:
    """Fetch original → probe → renditions → persist. Retries via ARQ."""
    from sqlalchemy import select

    from app import db
    from app.services.storage import get_storage

    try:
        asset_id = UUID(payload["asset_id"])
    except (KeyError, ValueError):
        raise AppError("internal_error", "process_media needs asset_id.", 500) from None

    storage = get_storage()
    async with db.session_scope() as session:
        asset = await session.get(MediaAsset, asset_id)
        if asset is None or asset.deleted_at is not None:
            logger.info("process_media: asset gone, skipping")
            return
        job = (await session.execute(
            select(MediaProcessingJob).where(MediaProcessingJob.asset_id == asset.id)
            .order_by(MediaProcessingJob.created_at.desc(), MediaProcessingJob.id.desc()).limit(1))).scalar_one_or_none()
        if job is None:
            logger.warning("process_media: no job row for asset=%s", asset.id)
            return
        if asset.status not in (MediaStatus.uploaded, MediaStatus.processing):
            return  # already resolved (idempotent re-delivery)
        asset.status = MediaStatus.processing
        job.status = JobStatus.running
        job.attempts += 1
        await session.flush()
        attempt = job.attempts

    try:
        raw = await storage.read_bytes(asset.original_key)
        digest = hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory(prefix="ml-media-") as tmp:
            workdir = Path(tmp)
            src = workdir / "original.bin"
            src.write_bytes(raw)
            if asset.kind == MediaKind.image:
                meta, renditions = await _process_image(asset, src, workdir)
            elif asset.kind == MediaKind.video:
                meta, renditions = await _process_video(asset, src, workdir)
            elif asset.kind == MediaKind.audio:
                meta, renditions = await _process_audio(asset, src, workdir)
            else:  # other/pdf: pass through, no derivatives
                meta, renditions = {"width": None, "height": None, "duration_ms": None}, []
    except ProcessingError as exc:
        await _record_failure(asset_id, str(exc), attempt)
        if attempt < MAX_ATTEMPTS:
            raise  # ARQ retries with backoff
        return
    except Exception:
        logger.exception("process_media unexpected failure asset=%s", asset_id)
        await _record_failure(asset_id, "Media processing failed unexpectedly.", attempt)
        if attempt < MAX_ATTEMPTS:
            raise
        return

    async with db.session_scope() as session:
        asset = await session.get(MediaAsset, asset_id)
        job = (await session.execute(
            select(MediaProcessingJob).where(MediaProcessingJob.asset_id == asset_id)
            .order_by(MediaProcessingJob.created_at.desc(), MediaProcessingJob.id.desc()).limit(1))).scalar_one()
        if asset is None or asset.deleted_at is not None:
            return
        asset.original_sha256 = digest
        asset.width = meta["width"]
        asset.height = meta["height"]
        asset.duration_ms = meta["duration_ms"]
        asset.derivatives = renditions
        asset.exif_stripped = True
        asset.status = MediaStatus.ready
        asset.failure_reason = None
        job.status = JobStatus.succeeded
        from datetime import datetime, timezone

        job.finished_at = datetime.now(timezone.utc)
    logger.info("processed asset=%s renditions=%d", asset_id, len(renditions))


async def _record_failure(asset_id: UUID, reason: str, attempt: int) -> None:
    from sqlalchemy import select

    from app import db

    async with db.session_scope() as session:
        asset = await session.get(MediaAsset, asset_id)
        job = (await session.execute(
            select(MediaProcessingJob).where(MediaProcessingJob.asset_id == asset_id)
            .order_by(MediaProcessingJob.created_at.desc(), MediaProcessingJob.id.desc()).limit(1))).scalar_one_or_none()
        if asset is None or job is None:
            return
        terminal = attempt >= MAX_ATTEMPTS
        asset.status = MediaStatus.failed if terminal else MediaStatus.uploaded
        asset.failure_reason = reason
        job.status = JobStatus.dead if terminal else JobStatus.failed
        job.last_error = reason
        from datetime import datetime, timezone

        if terminal:
            job.finished_at = datetime.now(timezone.utc)
    logger.info("process_media failure asset=%s terminal=%s: %s", asset_id, terminal, reason)

