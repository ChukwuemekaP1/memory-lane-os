"""Contributions service: posting, feeds, reactions, replies, moderation."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.logging import get_logger
from app.models.contributions import (
    Contribution,
    ContributionAttachment,
    MediaAsset,
)
from app.models.enums import (
    ContributionKind,
    ContributionStatus,
    MediaStatus,
    ModerationAction,
    ModerationTarget,
    ReplyStatus,
    ScheduledKind,
    ScheduledStatus,
)
from app.models.interactions import ModerationRecord, Reaction, Reply
from app.models.scheduling import ScheduledEvent
from app.models.users import User
from app.modules.permissions.actor import GuestActor, UserActor
from app.modules.permissions.capabilities import SpaceContext
from app.pagination import Cursor, normalize_limit
from app.services.jobs import JobRunner

logger = get_logger(__name__)

EMOJI_ALLOWLIST = frozenset({
    "❤", "🧡", "💛", "💚", "💙", "💜", "🖤", "🤍", "🤎", "💔", "❤️‍🔥",
    "👏", "🙏", "🎉", "🎂", "🥳", "😍", "😂", "😢", "😮", "👍",
})
TEXT_KINDS = {"message", "story", "private_note", "future_letter"}
SORTS = {"-created_at", "created_at", "-taken_at", "taken_at"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _kind(value: str) -> ContributionKind:
    try:
        return ContributionKind(value)
    except ValueError:
        valid = ", ".join(k.value for k in ContributionKind)
        raise AppError("validation_error", f"Invalid kind. Expected one of: {valid}.", 422) from None


def _effective_date(item: Contribution) -> datetime:
    return item.taken_at or item.created_at


async def _author_snapshot(session: AsyncSession, ctx: SpaceContext,
                           guest_name: str | None) -> tuple[str | None, str | None]:
    """Resolve (guest_name, author_snapshot) for a new post."""
    if isinstance(ctx.actor, UserActor):
        user = await session.get(User, ctx.actor.user_id)
        name = user.display_name if user else ctx.actor.display_name
        return None, (name or "Member")[:80]
    if guest_name:
        return guest_name, guest_name
    return None, None


async def create_contribution(
    session: AsyncSession, ctx: SpaceContext,
    kind: str, body: str | None, guest_name: str | None, is_anonymous: bool,
    is_private_to_owner: bool, taken_at: datetime | None, asset_ids: list[UUID],
    idempotency_key: str | None,
) -> tuple[Contribution, bool]:
    from app.modules.permissions import capabilities as caps

    caps.require_post(ctx)
    parsed_kind = _kind(kind)

    if idempotency_key:
        existing = await session.execute(select(Contribution).where(
            Contribution.space_id == ctx.space.id,
            Contribution.idempotency_key == idempotency_key,
            Contribution.deleted_at.is_(None)))
        found = existing.scalar_one_or_none()
        if found is not None:
            return found, True

    if parsed_kind.value in TEXT_KINDS and not (body or "").strip():
        raise AppError("validation_error", f"{kind} contributions require a body.", 422)
    if parsed_kind.value in ("media", "audio") and not asset_ids:
        raise AppError("validation_error", f"{kind} contributions require uploads.", 422)
    if parsed_kind.value == "audio" and len(asset_ids) > 1:
        raise AppError("validation_error", "Audio posts carry a single recording.", 422)
    if is_anonymous and not ctx.space.allow_anonymous:
        raise AppError("forbidden", "Anonymous contributions are disabled here.", 403)
    if isinstance(ctx.actor, GuestActor) and not guest_name and not is_anonymous:
        raise AppError("validation_error",
                       "Guests must give a name or post anonymously.", 422)
    if parsed_kind == ContributionKind.private_note:
        is_private_to_owner = True
    delivery_at: datetime | None = None
    if parsed_kind == ContributionKind.future_letter:
        if taken_at is None:
            raise AppError("validation_error", "Future letters need a delivery date.", 422)
        delivery_at = taken_at if taken_at.tzinfo else taken_at.replace(tzinfo=timezone.utc)
        if delivery_at <= _utcnow():
            raise AppError("validation_error", "Delivery date must be in the future.", 422)

    assets: list[MediaAsset] = []
    for asset_id in asset_ids:
        asset = await session.get(MediaAsset, asset_id)
        if asset is None or asset.space_id != ctx.space.id or asset.deleted_at is not None:
            raise AppError("not_found", "Upload not found.", 404)
        if not _owns_asset(ctx, asset):
            raise AppError("forbidden", "You may only attach your own uploads.", 403)
        if asset.status == MediaStatus.failed:
            raise AppError("conflict", "An upload failed processing; retry it first.", 409)
        if asset.status == MediaStatus.reserved:
            raise AppError("conflict", "An upload is not finished yet.", 409)
        assets.append(asset)

    name, snapshot = await _author_snapshot(session, ctx, guest_name)
    pre_moderated = ctx.space.moderation_mode.value == "pre"
    item = Contribution(
        space_id=ctx.space.id,
        author_user_id=ctx.user_id,
        guest_token_id=ctx.guest_token_id,
        guest_name=name,
        author_snapshot=snapshot,
        kind=parsed_kind,
        body=(body.strip() if body else None),
        status=(ContributionStatus.pending if (pre_moderated or parsed_kind
                == ContributionKind.future_letter) else ContributionStatus.visible),
        is_anonymous=is_anonymous,
        is_private_to_owner=is_private_to_owner,
        taken_at=taken_at,
        idempotency_key=idempotency_key,
    )
    session.add(item)
    await session.flush()
    for position, asset in enumerate(assets):
        session.add(ContributionAttachment(contribution_id=item.id, asset_id=asset.id,
                                           position=position))
    if parsed_kind == ContributionKind.future_letter and delivery_at is not None:
        assert delivery_at is not None
        session.add(ScheduledEvent(
            space_id=ctx.space.id, kind=ScheduledKind.future_letter, run_at=delivery_at,
            timezone=ctx.space.timezone,
            payload={"space_id": str(ctx.space.id), "contribution_id": str(item.id)},
            status=ScheduledStatus.scheduled, attempts=0,
            idempotency_key=f"letter:{item.id}:v1",
        ))
    await session.flush()
    logger.info("contribution created space=%s kind=%s", ctx.space.id, parsed_kind.value)
    return item, False


def _owns_asset(ctx: SpaceContext, asset: MediaAsset) -> bool:
    if ctx.user_id is not None and asset.uploader_user_id == ctx.user_id:
        return True
    return ctx.guest_token_id is not None and asset.guest_token_id == ctx.guest_token_id


def _author_match(ctx: SpaceContext):  # type: ignore[no-untyped-def]
    clauses = []
    if ctx.user_id is not None:
        clauses.append(Contribution.author_user_id == ctx.user_id)
    if ctx.guest_token_id is not None:
        clauses.append(Contribution.guest_token_id == ctx.guest_token_id)
    if not clauses:
        return None
    return or_(*clauses)


def visibility_filter(ctx: SpaceContext):  # type: ignore[no-untyped-def]
    """SQL mirror of capabilities.can_view_item (list queries)."""
    if ctx.is_owner or ctx.via_admin:
        return None
    author = _author_match(ctx)
    if ctx.is_collaborator:
        # Staff minus private-to-owner (unless own).
        private_ok = [Contribution.is_private_to_owner.is_(False)]
        if author is not None:
            private_ok.append(author)
        return or_(*private_ok)
    visible_public = and_(
        Contribution.status == ContributionStatus.visible,
        Contribution.is_private_to_owner.is_(False),
    )
    if author is not None:
        return or_(visible_public, author)
    return visible_public


async def list_contributions(
    session: AsyncSession, ctx: SpaceContext, kind: str | None, q: str | None,
    taken_from: datetime | None, taken_to: datetime | None, author: str | None,
    sort: str, cursor: str | None, limit: int | None,
) -> tuple[list[Contribution], str | None]:
    if sort not in SORTS:
        raise AppError("validation_error", f"Invalid sort. Expected one of: {sorted(SORTS)}.", 422)
    page_size = normalize_limit(limit)
    conditions = [Contribution.space_id == ctx.space.id, Contribution.deleted_at.is_(None)]
    extra = visibility_filter(ctx)
    if extra is not None:
        conditions.append(extra)
    if kind:
        kinds = set()
        for raw in kind.split(","):
            kinds.add(_kind(raw.strip()).value)
        conditions.append(Contribution.kind.in_(list(kinds)))
    if q:
        needle = q.strip()
        conditions.append(or_(
            Contribution.body.op("%")(needle),  # pg_trgm similarity
            Contribution.body.ilike(f"%{needle}%"),
            Contribution.guest_name.ilike(f"%{needle}%"),
        ))
    effective = func.coalesce(Contribution.taken_at, Contribution.created_at)
    if taken_from is not None:
        conditions.append(effective >= taken_from)
    if taken_to is not None:
        conditions.append(effective <= taken_to)
    if author:
        conditions.append(or_(
            Contribution.guest_name.ilike(f"%{author}%"),
            Contribution.author_snapshot.ilike(f"%{author}%"),
        ))

    descending = sort.startswith("-")
    key_column = Contribution.created_at if "created" in sort else effective
    if cursor:
        parsed = Cursor.decode(cursor)  # raises AppError on malformed input
        pair = tuple_(key_column, Contribution.id)
        bound = (parsed.created_at, parsed.id)
        conditions.append(pair < bound if descending else pair > bound)

    order = [key_column.desc(), Contribution.id.desc()] if descending else [
        key_column.asc(), Contribution.id.asc()]
    result = await session.execute(
        select(Contribution).where(*conditions).order_by(*order).limit(page_size + 1))
    rows = list(result.scalars().all())
    next_cursor = None
    if len(rows) > page_size:
        rows = rows[:page_size]
        last = rows[-1]
        key_value = last.created_at if "created" in sort else _effective_date(last)
        if key_value.tzinfo is None:
            key_value = key_value.replace(tzinfo=timezone.utc)
        next_cursor = Cursor(created_at=key_value, id=last.id).encode()
    return rows, next_cursor


async def contribution_detail(
    session: AsyncSession, ctx: SpaceContext, item_id: UUID,
) -> dict:
    from app.modules import media as media_module
    from app.modules.permissions import capabilities as caps

    item = await session.get(Contribution, item_id)
    if item is None or item.space_id != ctx.space.id or item.deleted_at is not None:
        raise AppError("not_found", "Contribution not found.", 404)
    if not caps.can_view_item(ctx, item):
        raise AppError("not_found", "Contribution not found.", 404)

    attachments = (await session.execute(
        select(ContributionAttachment, MediaAsset)
        .join(MediaAsset, MediaAsset.id == ContributionAttachment.asset_id)
        .where(ContributionAttachment.contribution_id == item.id)
        .order_by(ContributionAttachment.position)
    )).all()
    attachment_out = []
    for link, asset in attachments:
        urls = await media_module.service.asset_view_urls(ctx, asset)
        attachment_out.append({
            "asset_id": str(asset.id), "kind": asset.kind.value, "mime": asset.original_mime,
            "bytes": asset.original_bytes, "width": asset.width, "height": asset.height,
            "duration_ms": asset.duration_ms, "status": asset.status.value,
            "caption": link.caption, "urls": urls,
        })
    reactions = (await session.execute(
        select(Reaction.emoji, func.count()).where(Reaction.contribution_id == item.id)
        .group_by(Reaction.emoji)
    )).all()
    mine: set[str] = set()
    if ctx.user_id is not None or ctx.guest_token_id is not None:
        own = await session.execute(select(Reaction.emoji).where(
            Reaction.contribution_id == item.id,
            or_(
                Reaction.reactor_user_id == ctx.user_id if ctx.user_id else False,
                Reaction.guest_token_id == ctx.guest_token_id if ctx.guest_token_id else False,
            )))
        mine = {row for (row,) in own.all()}
    reply_count = await session.scalar(select(func.count()).select_from(Reply).where(
        Reply.contribution_id == item.id, Reply.deleted_at.is_(None),
        Reply.status.in_(["visible", "hidden"]) if ctx.is_staff else Reply.status == "visible",
    ))
    reason = None
    if (ctx.is_staff or caps.is_author(ctx, item)) and item.status == ContributionStatus.rejected:
        latest = await session.execute(
            select(ModerationRecord).where(
                ModerationRecord.target_type == ModerationTarget.contribution,
                ModerationRecord.target_id == item.id,
                ModerationRecord.action == ModerationAction.reject,
            ).order_by(ModerationRecord.created_at.desc()).limit(1))
        record = latest.scalar_one_or_none()
        reason = record.reason if record else None

    return {
        "id": str(item.id), "kind": item.kind.value, "body": item.body,
        "display_name": caps.display_name(ctx, item),
        "is_anonymous": item.is_anonymous, "is_private_to_owner": item.is_private_to_owner,
        "status": item.status.value, "taken_at": _iso(item.taken_at),
        "created_at": _iso(item.created_at),
        "attachments": attachment_out,
        "reactions": [{"emoji": emoji, "count": count, "mine": emoji in mine}
                      for emoji, count in reactions],
        "reply_count": reply_count or 0,
        "rejection_reason": reason,
    }


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment is not None else None


async def contribution_card(
    session: AsyncSession, ctx: SpaceContext, item: Contribution,
) -> dict:
    """List-view projection (feeds call detail lazily per item)."""
    from app.modules.permissions import capabilities as caps

    attachments = await session.scalar(select(func.count()).select_from(
        ContributionAttachment).where(ContributionAttachment.contribution_id == item.id))
    reactions = await session.scalar(select(func.count()).select_from(Reaction).where(
        Reaction.contribution_id == item.id))
    replies = await session.scalar(select(func.count()).select_from(Reply).where(
        Reply.contribution_id == item.id, Reply.deleted_at.is_(None)))
    return {
        "id": str(item.id), "kind": item.kind.value, "body": item.body,
        "display_name": caps.display_name(ctx, item),
        "is_anonymous": item.is_anonymous, "is_private_to_owner": item.is_private_to_owner,
        "status": item.status.value, "taken_at": _iso(item.taken_at),
        "created_at": _iso(item.created_at),
        "attachment_count": attachments or 0, "reaction_count": reactions or 0,
        "reply_count": replies or 0,
    }


async def patch_contribution(
    session: AsyncSession, ctx: SpaceContext, item_id: UUID, body: str | None,
    taken_at: datetime | None,
) -> Contribution:
    from app.modules.permissions import capabilities as caps

    item = await session.get(Contribution, item_id)
    if item is None or item.space_id != ctx.space.id or item.deleted_at is not None:
        raise AppError("not_found", "Contribution not found.", 404)
    if not caps.can_view_item(ctx, item):
        raise AppError("not_found", "Contribution not found.", 404)
    if not caps.can_edit_item(ctx, item):
        raise AppError("forbidden", "You may not edit this contribution.", 403)
    if body is not None:
        if item.kind.value in ("media", "audio"):
            raise AppError("validation_error", "Media posts have no editable body.", 422)
        item.body = body.strip()
    if taken_at is not None:
        moment = taken_at if taken_at.tzinfo else taken_at.replace(tzinfo=timezone.utc)
        if item.kind == ContributionKind.future_letter and moment <= _utcnow():
            raise AppError("validation_error", "Delivery date must be in the future.", 422)
        item.taken_at = moment
        if item.kind == ContributionKind.future_letter:
            await _reschedule_letter(session, ctx, item, moment)
    await session.flush()
    return item


async def _reschedule_letter(
    session: AsyncSession, ctx: SpaceContext, item: Contribution, moment: datetime
) -> None:
    result = await session.execute(select(ScheduledEvent).where(
        ScheduledEvent.space_id == ctx.space.id,
        ScheduledEvent.kind == ScheduledKind.future_letter,
        ScheduledEvent.status == ScheduledStatus.scheduled))
    for event in result.scalars().all():
        if event.payload.get("contribution_id") == str(item.id):
            event.status = ScheduledStatus.cancelled
    session.add(ScheduledEvent(
        space_id=ctx.space.id, kind=ScheduledKind.future_letter, run_at=moment,
        timezone=ctx.space.timezone,
        payload={"space_id": str(ctx.space.id), "contribution_id": str(item.id)},
        status=ScheduledStatus.scheduled, attempts=0,
        idempotency_key=f"letter:{item.id}:{moment.isoformat()}",
    ))
    await session.flush()


async def delete_contribution(session: AsyncSession, ctx: SpaceContext, item_id: UUID) -> None:
    from app.modules.permissions import capabilities as caps

    item = await session.get(Contribution, item_id)
    if item is None or item.space_id != ctx.space.id or item.deleted_at is not None:
        raise AppError("not_found", "Contribution not found.", 404)
    if not caps.can_delete_item(ctx, item):
        raise AppError("not_found" if not caps.can_view_item(ctx, item) else "forbidden",
                       "Contribution not found." if not caps.can_view_item(ctx, item)
                       else "You may not delete this contribution.",
                       404 if not caps.can_view_item(ctx, item) else 403)
    item.deleted_at = _utcnow()
    await session.flush()
    logger.info("contribution deleted space=%s item=%s", ctx.space.id, item.id)


async def toggle_reaction(
    session: AsyncSession, ctx: SpaceContext, item_id: UUID, emoji: str, on: bool,
) -> bool:
    """Idempotent toggle. Returns True when the call changed something."""
    from app.modules.permissions import capabilities as caps

    if emoji not in EMOJI_ALLOWLIST:
        raise AppError("validation_error", "That reaction is not supported.", 422)
    item = await session.get(Contribution, item_id)
    if item is None or item.space_id != ctx.space.id or item.deleted_at is not None:
        raise AppError("not_found", "Contribution not found.", 404)
    if not caps.can_view_item(ctx, item):
        raise AppError("not_found", "Contribution not found.", 404)
    if item.status != ContributionStatus.visible and not ctx.is_staff:
        raise AppError("forbidden", "You may not react to this contribution.", 403)
    if not caps.can_react(ctx):
        raise AppError("forbidden", "You may not react here.", 403)
    filt = [Reaction.contribution_id == item.id, Reaction.emoji == emoji]
    if ctx.user_id is not None:
        filt.append(Reaction.reactor_user_id == ctx.user_id)
    elif ctx.guest_token_id is not None:
        filt.append(Reaction.guest_token_id == ctx.guest_token_id)
    else:
        raise AppError("unauthenticated", "Authentication required.", 401)
    existing = (await session.execute(select(Reaction).where(*filt))).scalar_one_or_none()
    if on:
        if existing is not None:
            return False
        session.add(Reaction(contribution_id=item.id, reactor_user_id=ctx.user_id,
                             guest_token_id=ctx.guest_token_id, emoji=emoji))
        await session.flush()
        return True
    if existing is not None:
        await session.delete(existing)
        await session.flush()
        return True
    return False


async def list_replies(session: AsyncSession, ctx: SpaceContext, item_id: UUID) -> list[dict]:
    from app.modules.permissions import capabilities as caps

    item = await session.get(Contribution, item_id)
    if item is None or item.space_id != ctx.space.id or item.deleted_at is not None:
        raise AppError("not_found", "Contribution not found.", 404)
    if not caps.can_view_item(ctx, item):
        raise AppError("not_found", "Contribution not found.", 404)
    result = await session.execute(
        select(Reply).where(Reply.contribution_id == item.id, Reply.deleted_at.is_(None),
                            Reply.status.in_(["visible", "hidden"])
                            if ctx.is_staff else Reply.status == "visible")
        .order_by(Reply.created_at))
    out = []
    for reply in result.scalars().all():
        name = reply.guest_name
        if reply.author_user_id is not None:
            author = await session.get(User, reply.author_user_id)
            name = author.display_name if author else "Member"
        out.append({"id": str(reply.id), "display_name": name, "body": reply.body,
                    "status": reply.status.value, "created_at": _iso(reply.created_at)})
    return out


async def create_reply(
    session: AsyncSession, ctx: SpaceContext, item_id: UUID, body: str, guest_name: str | None,
) -> Reply:
    from app.modules.permissions import capabilities as caps

    item = await session.get(Contribution, item_id)
    if item is None or item.space_id != ctx.space.id or item.deleted_at is not None:
        raise AppError("not_found", "Contribution not found.", 404)
    if not caps.can_view_item(ctx, item):
        raise AppError("not_found", "Contribution not found.", 404)
    if not caps.can_reply(ctx):
        raise AppError("forbidden", "You may not reply here.", 403)
    if isinstance(ctx.actor, GuestActor) and not guest_name:
        raise AppError("validation_error", "Guests must give a name to reply.", 422)
    reply = Reply(contribution_id=item.id, author_user_id=ctx.user_id,
                  guest_token_id=ctx.guest_token_id, guest_name=guest_name,
                  body=body.strip(), status=ReplyStatus.visible)
    session.add(reply)
    await session.flush()
    return reply


async def delete_reply(session: AsyncSession, ctx: SpaceContext, reply_id: UUID) -> None:
    from app.modules.permissions import capabilities as caps

    reply = await session.get(Reply, reply_id)
    if reply is None or reply.deleted_at is not None:
        raise AppError("not_found", "Reply not found.", 404)
    item = await session.get(Contribution, reply.contribution_id)
    if item is None or item.space_id != ctx.space.id:
        raise AppError("not_found", "Reply not found.", 404)
    own = ((ctx.user_id is not None and reply.author_user_id == ctx.user_id)
           or (ctx.guest_token_id is not None and reply.guest_token_id == ctx.guest_token_id))
    if not (ctx.is_staff or own):
        raise AppError("forbidden", "You may not delete this reply.", 403)
    reply.deleted_at = _utcnow()
    await session.flush()


async def report_contribution(
    session: AsyncSession, ctx: SpaceContext, item_id: UUID, reason: str, jobs: JobRunner,
) -> None:
    """v1 reports: staff are notified by email (persistent report queue later)."""
    from app.modules.permissions import capabilities as caps

    if ctx.actor is None:
        raise AppError("unauthenticated", "Sign in or open the invite link to report.", 401)
    item = await session.get(Contribution, item_id)
    if item is None or item.space_id != ctx.space.id or item.deleted_at is not None:
        raise AppError("not_found", "Contribution not found.", 404)
    if not caps.can_view_item(ctx, item):
        raise AppError("not_found", "Contribution not found.", 404)
    owner = await session.get(User, ctx.space.owner_id)
    if owner is not None:
        await jobs.enqueue(
            "send_email",
            {
                "to": owner.email,
                "subject": f"Content reported in '{ctx.space.title}'",
                "template": "report_v1",
                "text_body": (
                    f"A {item.kind.value} contribution was reported.\nReason: {reason}\n"
                    f"Contribution: {item.id}\n"
                ),
            },
            idempotency_key=f"report:{item.id}:{ctx.user_id or ctx.guest_token_id}",
        )
    logger.info("contribution reported space=%s item=%s", ctx.space.id, item.id)


async def moderation_queue(session: AsyncSession, ctx: SpaceContext) -> list[dict]:
    from app.modules.permissions import capabilities as caps

    caps.require_staff(ctx)
    result = await session.execute(
        select(Contribution).where(
            Contribution.space_id == ctx.space.id, Contribution.deleted_at.is_(None),
            Contribution.status == ContributionStatus.pending)
        .order_by(Contribution.created_at))
    return [await contribution_card(session, ctx, item) for item in result.scalars().all()]


async def moderate(
    session: AsyncSession, ctx: SpaceContext, target_type: str, target_id: UUID,
    action: str, reason: str | None, jobs: JobRunner,
) -> dict:
    from app.modules.permissions import capabilities as caps

    caps.require_staff(ctx)
    try:
        parsed_target = ModerationTarget(target_type)
        parsed_action = ModerationAction(action)
    except ValueError:
        raise AppError("validation_error", "Invalid moderation target or action.", 422) from None

    if parsed_target == ModerationTarget.contribution:
        item = await session.get(Contribution, target_id)
        if item is None or item.space_id != ctx.space.id:
            raise AppError("not_found", "Contribution not found.", 404)
        if parsed_action == ModerationAction.approve:
            item.status = ContributionStatus.visible
        elif parsed_action == ModerationAction.hide:
            item.status = ContributionStatus.hidden
        elif parsed_action == ModerationAction.reject:
            item.status = ContributionStatus.rejected
            await _notify_author(session, ctx, item, reason, jobs)
        else:  # restore
            item.status = ContributionStatus.visible
        status_value = item.status.value
    else:
        reply = await session.get(Reply, target_id)
        if reply is None:
            raise AppError("not_found", "Reply not found.", 404)
        parent = await session.get(Contribution, reply.contribution_id)
        if parent is None or parent.space_id != ctx.space.id:
            raise AppError("not_found", "Reply not found.", 404)
        if parsed_action == ModerationAction.reject:
            raise AppError("validation_error", "Replies cannot be rejected; hide them.", 422)
        if parsed_action == ModerationAction.hide:
            reply.status = ReplyStatus.hidden
        else:  # approve / restore
            reply.status = ReplyStatus.visible
        status_value = reply.status.value

    session.add(ModerationRecord(
        space_id=ctx.space.id, target_type=parsed_target, target_id=target_id,
        action=parsed_action, reason=reason, acted_by=ctx.user_id,
        rule="staff" if not ctx.via_admin else "admin",
    ))
    await session.flush()
    logger.info("moderated space=%s target=%s action=%s", ctx.space.id, target_id, action)
    return {"status": status_value}


async def _notify_author(
    session: AsyncSession, ctx: SpaceContext, item: Contribution, reason: str | None,
    jobs: JobRunner,
) -> None:
    if item.author_user_id is None:
        return  # anonymous/link guests have no address; reason shows in-app
    author = await session.get(User, item.author_user_id)
    if author is None:
        return
    await jobs.enqueue(
        "send_email",
        {
            "to": author.email,
            "subject": f"An update on your contribution to '{ctx.space.title}'",
            "template": "moderation_v1",
            "text_body": (
                f"Your contribution was not approved for '{ctx.space.title}'."
                + (f"\nReason: {reason}\n" if reason else "\n")
            ),
        },
        idempotency_key=f"modrej:{item.id}",
    )


async def suggest_tag(
    session: AsyncSession, ctx: SpaceContext, item_id: UUID, label: str,
    user_id: UUID | None,
) -> dict:
    """Suggest a who-is-in-this-memory tag. Consent rules: self-tags and
    staff name-labels approve immediately; linked members approve their own
    tags; everything else pends staff review."""
    from app.models.interactions import ContributionTag
    from app.models.enums import TagStatus
    from app.modules.permissions import capabilities as caps

    item = await session.get(Contribution, item_id)
    if item is None or item.space_id != ctx.space.id or item.deleted_at is not None:
        raise AppError("not_found", "Contribution not found.", 404)
    if not caps.can_view_item(ctx, item):
        raise AppError("not_found", "Contribution not found.", 404)
    if ctx.actor is None:
        raise AppError("unauthenticated", "Authentication required.", 401)
    label = (label or "").strip()
    if not label or len(label) > 80:
        raise AppError("validation_error", "Tag label must be 1-80 chars.", 422)
    linked: User | None = None
    if user_id is not None:
        linked = await session.get(User, user_id)
        if linked is None or linked.deleted_at is not None:
            raise AppError("not_found", "Tagged user not found.", 404)
        if not await _is_space_person(session, ctx, user_id):
            raise AppError("forbidden", "Only space members can be tagged.", 403)
    if linked is not None and ctx.user_id == linked.id:
        status = TagStatus.approved  # self-tag
    elif linked is None and ctx.is_staff:
        status = TagStatus.approved  # staff name label
    else:
        status = TagStatus.pending
    tag = ContributionTag(
        contribution_id=item.id, label=label[:80], user_id=linked.id if linked else None,
        suggested_by_user_id=ctx.user_id, suggested_by_token_id=ctx.guest_token_id,
        status=status)
    session.add(tag)
    await session.flush()
    return _tag_out(ctx, tag)


async def _is_space_person(session: AsyncSession, ctx: SpaceContext, user_id: UUID) -> bool:
    from app.models.spaces import SpaceMembership

    if user_id == ctx.space.owner_id:
        return True
    result = await session.execute(select(SpaceMembership).where(
        SpaceMembership.space_id == ctx.space.id, SpaceMembership.user_id == user_id))
    return result.scalar_one_or_none() is not None


def _tag_out(ctx: SpaceContext, tag) -> dict:  # type: ignore[no-untyped-def]
    return {"id": str(tag.id), "label": tag.label,
            "user_id": str(tag.user_id) if tag.user_id else None,
            "status": tag.status.value, "created_at": _iso(tag.created_at)}


async def list_tags(session: AsyncSession, ctx: SpaceContext, item_id: UUID) -> list[dict]:
    from app.models.enums import TagStatus
    from app.models.interactions import ContributionTag
    from app.modules.permissions import capabilities as caps

    item = await session.get(Contribution, item_id)
    if item is None or item.space_id != ctx.space.id or item.deleted_at is not None:
        raise AppError("not_found", "Contribution not found.", 404)
    if not caps.can_view_item(ctx, item):
        raise AppError("not_found", "Contribution not found.", 404)
    result = await session.execute(
        select(ContributionTag).where(ContributionTag.contribution_id == item.id)
        .order_by(ContributionTag.created_at))
    out = []
    for tag in result.scalars().all():
        if tag.status == TagStatus.approved or ctx.is_staff:
            out.append(_tag_out(ctx, tag))
        elif ctx.user_id is not None and tag.user_id == ctx.user_id:
            out.append(_tag_out(ctx, tag))  # tagged user sees own pending tag
        elif ctx.user_id is not None and tag.suggested_by_user_id == ctx.user_id:
            out.append(_tag_out(ctx, tag))
        elif ctx.guest_token_id is not None and tag.suggested_by_token_id == ctx.guest_token_id:
            out.append(_tag_out(ctx, tag))
    return out


async def decide_tag(session: AsyncSession, ctx: SpaceContext, tag_id: UUID,
                     approve: bool) -> dict:
    from app.models.enums import TagStatus
    from app.models.interactions import ContributionTag

    tag = await session.get(ContributionTag, tag_id)
    if tag is None:
        raise AppError("not_found", "Tag not found.", 404)
    item = await session.get(Contribution, tag.contribution_id)
    if item is None or item.space_id != ctx.space.id:
        raise AppError("not_found", "Tag not found.", 404)
    mine = ctx.user_id is not None and tag.user_id == ctx.user_id
    if approve:
        if not (mine or (tag.user_id is None and ctx.is_staff)):
            raise AppError("forbidden", "Only the tagged person can approve.", 403)
        tag.status = TagStatus.approved
    else:
        if not (mine or ctx.is_staff):
            raise AppError("forbidden", "You may not decline this tag.", 403)
        tag.status = TagStatus.declined
    await session.flush()
    return _tag_out(ctx, tag)


async def delete_tag(session: AsyncSession, ctx: SpaceContext, tag_id: UUID) -> None:
    from app.models.interactions import ContributionTag

    tag = await session.get(ContributionTag, tag_id)
    if tag is None:
        raise AppError("not_found", "Tag not found.", 404)
    item = await session.get(Contribution, tag.contribution_id)
    if item is None or item.space_id != ctx.space.id:
        raise AppError("not_found", "Tag not found.", 404)
    own_suggestion = ((ctx.user_id is not None and tag.suggested_by_user_id == ctx.user_id)
                      or (ctx.guest_token_id is not None
                          and tag.suggested_by_token_id == ctx.guest_token_id))
    if not (ctx.is_staff or own_suggestion):
        raise AppError("forbidden", "You may not remove this tag.", 403)
    await session.delete(tag)
    await session.flush()


async def moderation_log(session: AsyncSession, ctx: SpaceContext) -> list[dict]:
    from app.modules.permissions import capabilities as caps

    caps.require_staff(ctx)
    result = await session.execute(
        select(ModerationRecord).where(ModerationRecord.space_id == ctx.space.id)
        .order_by(ModerationRecord.created_at.desc()).limit(100))
    return [{
        "id": str(record.id), "target_type": record.target_type.value,
        "target_id": str(record.target_id), "action": record.action.value,
        "reason": record.reason, "rule": record.rule, "created_at": _iso(record.created_at),
    } for record in result.scalars().all()]
