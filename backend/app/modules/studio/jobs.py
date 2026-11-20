"""Studio executor: runs AI jobs with retries, usage recording, and film render."""

from __future__ import annotations

import asyncio
import json
import random
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.errors import AppError
from app.logging import get_logger
from app.models.ai import AIGeneratedAsset, AIGenerationJob
from app.models.contributions import Contribution, MediaAsset
from app.models.enums import AIJobStatus, AIKind, MediaKind, MediaStatus, UsageKind
from app.services.ai.providers import AIError, AIProvider, AIResult, get_ai_provider
from app.services.ai.quota import record_usage
from app.services.jobs import job

logger = get_logger(__name__)

USAGE_BY_KIND = {
    AIKind.transcription: UsageKind.ai_transcription,
    AIKind.captions: UsageKind.ai_vision,
    AIKind.highlight_film: UsageKind.ai_film,
    AIKind.categorization: UsageKind.ai_text,
    AIKind.summary: UsageKind.ai_text,
    AIKind.letter: UsageKind.ai_text,
    AIKind.book: UsageKind.ai_text,
    AIKind.image_generation: UsageKind.ai_image,
    AIKind.story_enhancement: UsageKind.ai_text,
}
MAX_INPUT_ITEMS = 200
MAX_BODY_CHARS = 2000


@job("ai_run")
async def ai_run_job(payload: dict[str, Any]) -> None:
    from app import db

    try:
        job_id = UUID(payload["job_id"])
    except (KeyError, ValueError):
        raise AppError("internal_error", "ai_run needs job_id.", 500) from None
    from datetime import datetime, timezone

    settings = get_settings()
    async with db.session_scope() as session:
        job = await session.get(AIGenerationJob, job_id)
        if job is None or job.status == AIJobStatus.cancelled:
            return
        if job.status not in (AIJobStatus.queued, AIJobStatus.running):
            return  # idempotent re-delivery
        job.status = AIJobStatus.running
        job.attempts += 1
        if job.started_at is None:
            job.started_at = datetime.now(timezone.utc)
        await session.flush()

    provider = get_ai_provider(settings)
    try:
        total = await _execute_with_retry(settings, provider, job_id)
    except AIError as exc:
        # Retryable errors were already retried inline; record the outcome.
        await _record_failure(job_id, exc.message)
        return
    except Exception:
        logger.exception("ai_run unexpected failure job=%s", job_id)
        await _record_failure(job_id, "AI processing failed unexpectedly.")
        return
    await _record_success(job_id, total)


async def _execute_with_retry(settings: Settings, provider: AIProvider, job_id: UUID) -> int:
    last_error: AIError | None = None
    for attempt in range(1, settings.ai_max_attempts + 1):
        try:
            return await _execute_once(provider, job_id, settings)
        except AIError as exc:
            last_error = exc
            if not exc.retryable or attempt >= settings.ai_max_attempts:
                raise
            delay = settings.ai_retry_base_seconds * (2 ** (attempt - 1))
            delay += random.uniform(0, delay * 0.2)
            logger.info("ai retry job=%s attempt=%d sleep=%.1f", job_id, attempt, delay)
            await asyncio.sleep(delay)
    assert last_error is not None
    raise last_error


async def _execute_once(provider: AIProvider, job_id: UUID, settings: Settings) -> int:
    from app import db

    async with db.session_scope() as session:
        job = await session.get(AIGenerationJob, job_id)
        assert job is not None
        if job.status == AIJobStatus.cancelled:
            return 0
        handler = _HANDLERS[job.kind]
        total = await handler(session, provider, job, settings)
        return total


async def _record_failure(job_id: UUID, reason: str) -> None:
    from datetime import datetime, timezone

    from app import db

    async with db.session_scope() as session:
        job = await session.get(AIGenerationJob, job_id)
        if job is None:
            return
        job.status = AIJobStatus.dead
        job.last_error = reason[:500]
        job.finished_at = datetime.now(timezone.utc)
        job.quota_reserved = 0


async def _record_success(job_id: UUID, total_tokens: int) -> None:
    from datetime import datetime, timezone

    from app import db

    async with db.session_scope() as session:
        job = await session.get(AIGenerationJob, job_id)
        if job is None or job.status == AIJobStatus.cancelled:
            return
        job.status = AIJobStatus.succeeded
        job.finished_at = datetime.now(timezone.utc)
        job.quota_reserved = 0
        if job.requested_by is not None and total_tokens > 0:
            await record_usage(session, job.requested_by, job.space_id,
                               USAGE_BY_KIND[job.kind], total_tokens,
                               "ai_generation_jobs", job.id, f"use:{job.id}")


def _parse_json(text: str, what: str) -> Any:
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        raise AIError(f"AI returned invalid {what}.", retryable=True) from None


async def _eligible_items(session: AsyncSession, job: AIGenerationJob,
                          ids: list[str] | None) -> list[Contribution]:
    from app.models.enums import ContributionStatus

    query = select(Contribution).where(
        Contribution.space_id == job.space_id, Contribution.deleted_at.is_(None),
        Contribution.status == ContributionStatus.visible,
        Contribution.is_private_to_owner.is_(False))
    if ids:
        query = query.where(Contribution.id.in_([UUID(raw) for raw in ids]))
    query = query.order_by(Contribution.created_at).limit(MAX_INPUT_ITEMS)
    return list((await session.execute(query)).scalars().all())


def _serialize(items: list[Contribution]) -> str:
    lines = []
    for item in items:
        name = item.guest_name or item.author_snapshot or "Someone"
        body = (item.body or f"[{item.kind.value}]")[:MAX_BODY_CHARS]
        lines.append(f"- {name}: {body}")
    return "\n".join(lines)


async def _save_asset(session: AsyncSession, job: AIGenerationJob, title: str | None,
                      text_body: str | None = None, asset_id: UUID | None = None,
                      edit_list: dict | None = None) -> AIGeneratedAsset:
    asset = AIGeneratedAsset(job_id=job.id, space_id=job.space_id, kind=job.kind,
                             title=title, text_body=text_body, asset_id=asset_id,
                             edit_list=edit_list, is_promoted=False, is_ai_labeled=True)
    session.add(asset)
    await session.flush()
    return asset


def _record_outcome(job: AIGenerationJob, outcome: AIResult) -> None:
    from decimal import Decimal

    if outcome.model:
        job.model = outcome.model
    job.input_tokens = (job.input_tokens or 0) + outcome.input_tokens
    job.output_tokens = (job.output_tokens or 0) + outcome.output_tokens
    if outcome.cost_usd is not None:
        prev = job.cost_usd or Decimal("0")
        job.cost_usd = prev + Decimal(str(round(outcome.cost_usd, 6)))


async def _handle_transcription(session: AsyncSession, provider: AIProvider,
                                job: AIGenerationJob, settings: Settings) -> int:
    from app.services.storage import get_storage

    asset_ids = [UUID(raw) for raw in job.inputs.get("asset_ids", [])]
    language = str(job.inputs.get("language") or "en")[:16]
    result = await session.execute(select(MediaAsset).where(MediaAsset.id.in_(asset_ids)))
    assets = list(result.scalars().all())
    if len(assets) != len(asset_ids):
        raise AIError("An upload was not found.", retryable=False, code="refused")
    storage = get_storage()
    total = 0
    for asset in assets:
        if asset.space_id != job.space_id or asset.status != MediaStatus.ready:
            raise AIError("All uploads must finish processing first.",
                          retryable=False, code="refused")
        raw = await storage.read_bytes(asset.original_key)
        if len(raw) > 25 * 1024 * 1024:
            raise AIError("Audio over 25 MB cannot be transcribed.", retryable=False,
                          code="refused")
        outcome = await provider.transcribe(raw, asset.original_mime, language=language)
        _record_outcome(job, outcome)
        total += outcome.total_tokens
        await _save_asset(session, job, title=f"Transcript ({asset.original_mime})",
                          text_body=outcome.text, asset_id=asset.id)
    return total


async def _handle_categorization(session: AsyncSession, provider: AIProvider,
                                 job: AIGenerationJob, settings: Settings) -> int:
    items = await _eligible_items(session, job, job.inputs.get("contribution_ids"))
    if not items:
        await _save_asset(session, job, title="Categories", text_body="{}")
        return 0
    outcome = await provider.complete_text(
        "Categorize memories. Reply with JSON only: {\"categories\": [\"...\"]}.",
        f"Categorize these memories (5 max, lowercase, single words):\n{_serialize(items)}",
        json_mode=True, max_tokens=settings.ai_max_output_tokens)
    _record_outcome(job, outcome)
    data = _parse_json(outcome.text, "categories")
    categories = [str(cat).strip().lower()[:40] for cat in data.get("categories", [])][:5]
    for item in items:
        item.ai_categories = categories
    await _save_asset(session, job, title="Categories",
                      text_body=json.dumps({"categories": categories,
                                            "count": len(items)}))
    return outcome.total_tokens


async def _handle_captions(session: AsyncSession, provider: AIProvider,
                           job: AIGenerationJob, settings: Settings) -> int:
    from app.services.storage import get_storage

    asset_ids = [UUID(raw) for raw in job.inputs.get("asset_ids", [])]
    result = await session.execute(select(MediaAsset).where(MediaAsset.id.in_(asset_ids)))
    assets = [a for a in result.scalars().all()
              if a.space_id == job.space_id and a.status == MediaStatus.ready]
    if len(assets) != len(asset_ids):
        raise AIError("All uploads must finish processing first.", retryable=False,
                      code="refused")
    storage = get_storage()
    images, mimes = [], []
    for asset in assets[:4]:
        # Prefer small derivatives over originals (cost + privacy hygiene).
        key, mime = asset.original_key, asset.original_mime
        for rendition in asset.derivatives or []:
            if rendition.get("label") == "thumb":
                key, mime = rendition["key"], rendition.get("mime", mime)
        images.append(await storage.read_bytes(key))
        mimes.append(mime)
    outcome = await provider.complete_vision(
        "Analyze the provided photos accurately. Do not invent or assume details that "
        "cannot be established from the image. Reply with JSON only: "
        "{\"captions\": [\"...\"], \"descriptions\": [\"...\"], \"categories\": [\"...\"]}.",
        f"Provide one concise grounded caption and description per photo ({len(images)} photos) "
        "plus up to 5 lowercase single-word categories.",
        images, mimes, json_mode=True, max_tokens=settings.ai_max_output_tokens)
    _record_outcome(job, outcome)
    data = _parse_json(outcome.text, "captions")
    captions = [str(cap)[:500] for cap in data.get("captions", [])]
    descriptions = [str(d)[:500] for d in data.get("descriptions", [])]
    categories = [str(c).strip().lower()[:40] for c in data.get("categories", [])][:5]
    await _save_asset(session, job, title="Caption suggestions",
                      text_body=json.dumps({"captions": captions,
                                            "descriptions": descriptions,
                                            "categories": categories,
                                            "asset_ids": [str(a.id) for a in assets]}))
    return outcome.total_tokens


async def _handle_summary(session: AsyncSession, provider: AIProvider,
                          job: AIGenerationJob, settings: Settings) -> int:
    items = await _eligible_items(session, job, job.inputs.get("contribution_ids"))
    if not items:
        await _save_asset(session, job, title="Summary", text_body="No memories to summarize yet.")
        return 0
    outcome = await provider.complete_text(
        "You write warm, concise memory summaries grounded strictly in the provided memories.",
        f"Summarize these {len(items)} memories in a few heartfelt paragraphs:\n"
        f"{_serialize(items)}",
        json_mode=False, max_tokens=settings.ai_max_output_tokens)
    _record_outcome(job, outcome)
    await _save_asset(session, job, title="Memory summary", text_body=outcome.text)
    return outcome.total_tokens


async def _handle_letter(session: AsyncSession, provider: AIProvider,
                         job: AIGenerationJob, settings: Settings) -> int:
    items = await _eligible_items(session, job, job.inputs.get("contribution_ids"))
    tone = job.inputs.get("tone", "warm")
    to = job.inputs.get("to", "friend")
    sender = job.inputs.get("from", "all of us")
    outcome = await provider.complete_text(
        f"You write {tone} memory letters.",
        f"Write a {tone} memory letter to {to} from {sender}, drawing on these "
        f"memories:\n{_serialize(items)}",
        json_mode=False, max_tokens=settings.ai_max_output_tokens)
    _record_outcome(job, outcome)
    await _save_asset(session, job, title=f"Letter to {to}", text_body=outcome.text)
    return outcome.total_tokens


async def _handle_book(session: AsyncSession, provider: AIProvider,
                       job: AIGenerationJob, settings: Settings) -> int:
    sections = job.inputs.get("sections") or [{"title": "Our memories"}]
    items = await _eligible_items(session, job, job.inputs.get("contribution_ids"))
    compiled = []
    total = 0
    for section in sections[:12]:
        section_items = items
        if section.get("contribution_ids"):
            section_items = await _eligible_items(session, job, section["contribution_ids"])
        outcome = await provider.complete_text(
            "You write memory-book chapters as JSON: {\"title\": ..., \"text\": ...}.",
            f"Write the '{section.get('title', 'Untitled')}' chapter from these "
            f"memories:\n{_serialize(section_items)}",
            json_mode=True, max_tokens=settings.ai_max_output_tokens)
        _record_outcome(job, outcome)
        total += outcome.total_tokens
        compiled.append(_parse_json(outcome.text, "chapter"))
    await _save_asset(session, job, title=job.inputs.get("title", "Memory book"),
                      text_body=json.dumps({"title": job.inputs.get("title", "Memory book"),
                                            "sections": compiled}))
    return total


async def _handle_story_enhancement(session: AsyncSession, provider: AIProvider,
                                    job: AIGenerationJob, settings: Settings) -> int:
    items = await _eligible_items(session, job, job.inputs.get("contribution_ids"))
    tone = str(job.inputs.get("tone") or "warm")[:40]
    if not items:
        await _save_asset(session, job, title="Enhanced story", text_body="{}")
        return 0
    outcome = await provider.complete_text(
        f"Polish and enhance memory stories in a {tone} voice without inventing new facts. "
        "Reply with JSON only: {\"title\": \"...\", \"enhanced_story\": \"...\", \"highlights\": [\"...\"]}.",
        f"Enhance these memories into a cohesive story:\n{_serialize(items)}",
        json_mode=True, max_tokens=settings.ai_max_output_tokens)
    _record_outcome(job, outcome)
    data = _parse_json(outcome.text, "enhanced story")
    title = str(data.get("title") or "Enhanced story")[:200]
    await _save_asset(session, job, title=title, text_body=json.dumps(data))
    return outcome.total_tokens


async def _handle_image_generation(session: AsyncSession, provider: AIProvider,
                                   job: AIGenerationJob, settings: Settings) -> int:
    import hashlib
    import mimetypes
    from app.models.spaces import Space
    from app.services.storage import get_storage

    prompt = str(job.inputs.get("prompt") or "").strip()
    aspect_ratio = job.inputs.get("aspect_ratio")
    outcome = await provider.generate_image(
        prompt, aspect_ratio=str(aspect_ratio) if aspect_ratio else None
    )
    _record_outcome(job, outcome)
    img_bytes, img_mime = outcome.images[0]
    ext = mimetypes.guess_extension(img_mime.split(";")[0].strip()) or ".png"

    media = MediaAsset(
        space_id=job.space_id,
        uploader_user_id=job.requested_by,
        kind=MediaKind.image,
        original_key="",
        original_bytes=len(img_bytes),
        original_mime=img_mime,
        original_sha256=hashlib.sha256(img_bytes).hexdigest(),
        derivatives=[],
        status=MediaStatus.ready,
    )
    session.add(media)
    await session.flush()
    media.original_key = f"generated/{job.space_id}/{media.id}{ext}"

    storage = get_storage()
    await storage.write_bytes(media.original_key, img_bytes, img_mime)
    try:
        space = await session.get(Space, job.space_id)
        if space is not None:
            space.storage_used_bytes += len(img_bytes)
        await _save_asset(
            session,
            job,
            title=str(job.inputs.get("title") or "Generated memory artwork")[:200],
            text_body=outcome.text or prompt[:500],
            asset_id=media.id,
        )
    except Exception:
        await storage.delete(media.original_key)
        raise
    return outcome.total_tokens


async def _handle_highlight_film(session: AsyncSession, provider: AIProvider,
                                 job: AIGenerationJob, settings: Settings) -> int:
    from app.modules.studio.film import render_highlight_film, select_highlights

    asset_ids = [UUID(raw) for raw in job.inputs.get("asset_ids", [])]
    result = await session.execute(select(MediaAsset).where(MediaAsset.id.in_(asset_ids)))
    found = [a for a in result.scalars().all() if a.space_id == job.space_id]
    if len(found) != len(asset_ids):
        raise AIError("An upload was not found.", retryable=False, code="refused")
    assets = [a for a in found
              if a.status == MediaStatus.ready
              and a.kind in (MediaKind.video, MediaKind.image)]
    if not assets:
        raise AIError("No ready photo/video uploads to feature.", retryable=False,
                      code="refused")
    max_duration = int(job.inputs.get("max_duration_s", 60))
    edit_list, tokens = await select_highlights(provider, assets, max_duration, settings)
    film_asset_id = await render_highlight_film(session, job, assets, edit_list, settings)
    await _save_asset(session, job, title="Highlight film", asset_id=film_asset_id,
                      edit_list=edit_list)
    return tokens


_HANDLERS = {
    AIKind.transcription: _handle_transcription,
    AIKind.categorization: _handle_categorization,
    AIKind.captions: _handle_captions,
    AIKind.summary: _handle_summary,
    AIKind.letter: _handle_letter,
    AIKind.book: _handle_book,
    AIKind.highlight_film: _handle_highlight_film,
    AIKind.image_generation: _handle_image_generation,
    AIKind.story_enhancement: _handle_story_enhancement,
}
