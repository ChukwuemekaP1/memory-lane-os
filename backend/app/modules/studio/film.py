"""Highlight films: AI moment selection + deterministic FFmpeg assembly.

Selection asks the provider for clips; rendering trims video segments and
pans still images into normalized 720p segments, then concatenates them with
AAC audio. Anything unsupported (missing assets, no media, empty selection)
fails the job with an honest reason instead of a broken file.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.logging import get_logger
from app.models.ai import AIGenerationJob
from app.models.contributions import MediaAsset
from app.models.enums import MediaKind, MediaStatus
from app.services.ai.providers import AIError, AIProvider

logger = get_logger(__name__)

SEGMENT_SECONDS = 4
IMAGE_HOLD_SECONDS = 3


async def select_highlights(
    provider: AIProvider, assets: list[MediaAsset], max_duration_s: int,
    settings: Settings,
) -> tuple[dict[str, Any], int]:
    catalog = []
    for asset in assets[:20]:
        catalog.append({
            "asset_id": str(asset.id),
            "kind": asset.kind.value,
            "duration_ms": asset.duration_ms,
            "mime": asset.original_mime,
        })
    outcome = await provider.complete_text(
        "Pick highlight moments. Reply with JSON only: "
        "{\"clips\": [{\"asset_id\": ..., \"start_s\": ..., \"end_s\": ...}]}.",
        f"Select highlight clips totaling at most {max_duration_s}s from:\n"
        f"{json.dumps(catalog)}",
        json_mode=True, max_tokens=settings.ai_max_output_tokens)
    try:
        edit_list = json.loads(outcome.text)
    except (ValueError, TypeError):
        raise AIError("AI returned an invalid edit list.", retryable=True) from None
    clips = [clip for clip in edit_list.get("clips", []) if _valid_clip(clip, assets)]
    if not clips:
        # Honest fallback: chronological tour instead of a failed job.
        clips = _fallback_clips(assets, max_duration_s)
    edit_list["clips"] = clips[:12]
    return edit_list, outcome.total_tokens


def _valid_clip(clip: dict, assets: list[MediaAsset]) -> bool:
    by_id = {str(asset.id): asset for asset in assets}
    asset = by_id.get(str(clip.get("asset_id")))
    if asset is None:
        return False
    try:
        start = float(clip.get("start_s", 0))
        end = float(clip.get("end_s", 0))
    except (TypeError, ValueError):
        return False
    if asset.kind == MediaKind.image:
        return True
    duration_s = (asset.duration_ms or 0) / 1000
    return 0 <= start < end and (duration_s <= 0 or start < duration_s)


def _fallback_clips(assets: list[MediaAsset], max_duration_s: int) -> list[dict]:
    clips: list[dict] = []
    budget = max(4, min(max_duration_s, 180))
    per_asset = max(2, budget // max(1, len(assets)))
    for asset in assets:
        if asset.kind == MediaKind.image:
            clips.append({"asset_id": str(asset.id), "start_s": 0,
                          "end_s": IMAGE_HOLD_SECONDS})
        else:
            duration_s = (asset.duration_ms or 8000) / 1000
            end = min(duration_s, per_asset)
            clips.append({"asset_id": str(asset.id), "start_s": 0, "end_s": max(1, end)})
    return clips


async def render_highlight_film(
    session: AsyncSession, job: AIGenerationJob, assets: list[MediaAsset],
    edit_list: dict[str, Any], settings: Settings,
) -> UUID:
    from app.services.storage import get_storage

    clips = edit_list.get("clips", [])
    if not clips:
        raise AIError("No highlight moments could be selected.", retryable=False,
                      code="refused")
    storage = get_storage()
    by_id = {str(asset.id): asset for asset in assets}
    with tempfile.TemporaryDirectory(prefix="ml-film-") as tmp:
        workdir = Path(tmp)
        segments: list[Path] = []
        for index, clip in enumerate(clips):
            asset = by_id.get(str(clip.get("asset_id")))
            if asset is None:
                continue
            raw = await storage.read_bytes(asset.original_key)
            src = workdir / f"src-{index}.bin"
            src.write_bytes(raw)
            out = workdir / f"seg-{index}.mp4"
            if asset.kind == MediaKind.image:
                await _run_ffmpeg([
                    "-loop", "1", "-t", str(IMAGE_HOLD_SECONDS), "-i", str(src),
                    "-vf", "scale=1280:-2,format=yuv420p", "-c:v", "libx264",
                    "-preset", "veryfast", "-an", str(out),
                ], "image segment")
            else:
                start = float(clip.get("start_s", 0))
                length = max(1.0, float(clip.get("end_s", start + SEGMENT_SECONDS)) - start)
                await _run_ffmpeg([
                    "-ss", str(start), "-t", str(length), "-i", str(src),
                    "-vf", "scale=1280:-2,format=yuv420p", "-c:v", "libx264",
                    "-preset", "veryfast", "-c:a", "aac", str(out),
                ], "video segment")
            segments.append(out)
        if not segments:
            raise AIError("No clips could be rendered.", retryable=False, code="refused")
        concat = workdir / "concat.txt"
        concat.write_text("".join(f"file '{segment}'\n" for segment in segments))
        final = workdir / "highlight.mp4"
        await _run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat),
                           "-c", "copy", str(final)], "final cut")
        film_bytes = final.read_bytes()
        poster = workdir / "poster.jpg"
        await _run_ffmpeg(["-ss", "1", "-i", str(final), "-frames:v", "1", "-q:v", "5",
                           str(poster)], "film poster")
        poster_bytes = poster.read_bytes()

    film = MediaAsset(
        space_id=job.space_id, uploader_user_id=job.requested_by, kind=MediaKind.video,
        original_key="", original_bytes=len(film_bytes), original_mime="video/mp4",
        original_sha256="", derivatives=[], status=MediaStatus.ready,
    )
    session.add(film)
    await session.flush()
    film.original_key = f"generated/{job.space_id}/{film.id}/highlight.mp4"
    poster_key = f"derivatives/{job.space_id}/{film.id}/poster.jpg"
    await storage.write_bytes(film.original_key, film_bytes, "video/mp4")
    try:
        await storage.write_bytes(poster_key, poster_bytes, "image/jpeg")
        film.derivatives = [{"label": "poster", "key": poster_key, "mime": "image/jpeg",
                             "width": None, "height": None, "bytes": len(poster_bytes)}]
        import hashlib

        film.original_sha256 = hashlib.sha256(film_bytes).hexdigest()
        space = await _space_of(session, job)
        space.storage_used_bytes += len(film_bytes)
        await session.flush()
    except Exception:
        await storage.delete(film.original_key)
        await storage.delete(poster_key)
        raise
    logger.info("rendered highlight film job=%s bytes=%d", job.id, len(film_bytes))
    return film.id


async def _run_ffmpeg(args: list[str], label: str) -> None:
    from app.services.ffmpeg import MediaToolError
    from app.services.ffmpeg import run_ffmpeg as shared_run

    try:
        await shared_run(args, label)
    except MediaToolError as exc:
        raise AIError(str(exc), retryable=True) from None


async def _space_of(session: AsyncSession, job: AIGenerationJob):  # type: ignore[no-untyped-def]
    from app.models.spaces import Space

    space = await session.get(Space, job.space_id)
    assert space is not None
    return space
