"""Spaces service: CRUD, members, tokens, invitations, purge (API spec §7-8)."""

from __future__ import annotations

import secrets
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.errors import AppError
from app.logging import get_logger
from app.models.archives import Archive
from app.models.contributions import Contribution, MediaAsset
from app.models.enums import (
    ContributionPolicy,
    ContributionStatus,
    GuestRoleCap,
    ModerationMode,
    Plan,
    ScheduledKind,
    ScheduledStatus,
    SpaceKind,
    SpaceRole,
    SpaceVisibility,
)
from app.models.scheduling import ScheduledEvent
from app.models.spaces import GuestAccessToken, Invitation, Space, SpaceMembership, SpaceSettings, Theme
from app.models.users import User
from app.modules.identity import tokens as token_helpers
from app.modules.permissions.actor import GuestActor, UserActor
from app.modules.permissions.capabilities import SpaceContext, require_owner
from app.modules.spaces.schemas import SpaceCreateIn, SpacePatchIn
from app.services.jobs import JobRunner, job

logger = get_logger(__name__)

FREE_STORAGE_BYTES = 1_000_000_000
THEME_OVERRIDE_KEYS = {"accent", "background", "font", "layout", "cover_fit"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_enum(enum_cls, value: str, field: str):  # type: ignore[no-untyped-def]
    try:
        return enum_cls(value)
    except ValueError:
        valid = ", ".join(member.value for member in enum_cls)
        raise AppError("validation_error", f"Invalid {field}. Expected one of: {valid}.", 422) from None


def require_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise AppError("validation_error", f"Invalid timezone: {value}.", 422) from None
    return value


def _as_utc(moment: datetime, zone: str) -> datetime:
    """Interpret naive datetimes in the space timezone; convert to UTC."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=ZoneInfo(zone)).astimezone(timezone.utc)
    return moment.astimezone(timezone.utc)


async def owner_plan(session: AsyncSession, owner_id: UUID) -> Plan:
    from app.models.archives import Subscription

    result = await session.execute(
        select(Subscription.plan).where(
            Subscription.user_id == owner_id,
            Subscription.status.in_(["active", "past_due"]),
        )
    )
    plan = result.scalar_one_or_none()
    return plan if plan is not None else Plan.free


async def _get_theme_or_404(session: AsyncSession, theme_id: UUID) -> Theme:
    theme = await session.get(Theme, theme_id)
    if theme is None or not theme.is_active:
        raise AppError("not_found", "Theme not found.", 404)
    return theme


async def _require_theme_entitlement(session: AsyncSession, owner_id: UUID, theme: Theme) -> None:
    if theme.plan_required == Plan.free:
        return
    if await owner_plan(session, owner_id) != Plan.premium:
        raise AppError(
            "quota_exceeded", f"The '{theme.name}' theme requires a premium plan.", 403,
            details={"theme": theme.slug},
        )


def resolve_theme(space: Space, theme: Theme) -> tuple[Theme, dict, bool]:
    """Merge base tokens with space overrides (content/permissions untouched)."""
    overrides = space.theme_overrides or {}
    merged = {**theme.tokens, **overrides}
    return theme, merged, bool(overrides)


async def preview_theme(
    session: AsyncSession, ctx: SpaceContext, theme_id: UUID | None, overrides: dict | None,
) -> dict:
    """Resolve theme tokens without saving (any space viewer may preview)."""
    theme = await _get_theme_or_404(session, theme_id) if theme_id else await _get_theme_or_404(
        session, ctx.space.theme_id)
    clean = validate_theme_overrides(overrides or {})
    merged = {**theme.tokens, **clean}
    return {
        "theme": {
            "id": str(theme.id), "slug": theme.slug, "name": theme.name,
            "occasions": theme.occasions, "tokens": theme.tokens,
            "plan_required": theme.plan_required.value,
        },
        "tokens": merged,
        "is_customized": bool(clean) or theme.id != ctx.space.theme_id,
    }


def validate_theme_overrides(overrides: dict) -> dict:
    if not isinstance(overrides, dict):
        raise AppError("validation_error", "theme_overrides must be an object.", 422)
    for key, value in overrides.items():
        if key not in THEME_OVERRIDE_KEYS:
            raise AppError(
                "validation_error",
                f"Unknown theme key '{key}'. Allowed: {sorted(THEME_OVERRIDE_KEYS)}.", 422,
            )
        if not isinstance(value, str) or not (1 <= len(value) <= 40):
            raise AppError("validation_error", f"Theme value for '{key}' must be 1-40 chars.", 422)
    return overrides


def guest_url(space_id: UUID, raw_token: str, settings: Settings) -> str:
    return f"{settings.frontend_base_url.rstrip('/')}/s/{space_id}?guest={raw_token}"


async def _mint_token_row(
    session: AsyncSession, space: Space, created_by: UUID | None, created_by_email: str | None,
    label: str, role_cap: GuestRoleCap, max_uses: int | None = None,
    expires_at: datetime | None = None,
) -> tuple[GuestAccessToken, str]:
    raw = secrets.token_hex(32)
    token = GuestAccessToken(
        space_id=space.id, token_hash=token_helpers.sha256_hex(raw), label=label,
        role_cap=role_cap, max_uses=max_uses, use_count=0, expires_at=expires_at,
        created_by=created_by, created_by_email=created_by_email,
    )
    session.add(token)
    await session.flush()
    return token, raw


async def _schedule_reveal(
    session: AsyncSession, space: Space, run_at: datetime, version: int = 1
) -> ScheduledEvent:
    event = ScheduledEvent(
        space_id=space.id, kind=ScheduledKind.reveal, run_at=run_at,
        timezone=space.timezone, payload={"space_id": str(space.id)},
        status=ScheduledStatus.scheduled, attempts=0,
        idempotency_key=f"space:{space.id}:reveal:v{version}",
    )
    session.add(event)
    await session.flush()
    return event


async def _active_reveal(session: AsyncSession, space_id: UUID) -> ScheduledEvent | None:
    result = await session.execute(
        select(ScheduledEvent).where(
            ScheduledEvent.space_id == space_id,
            ScheduledEvent.kind == ScheduledKind.reveal,
            ScheduledEvent.status == ScheduledStatus.scheduled,
        )
    )
    return result.scalar_one_or_none()


async def _cancel_event(session: AsyncSession, event: ScheduledEvent) -> None:
    event.status = ScheduledStatus.cancelled
    await session.flush()


async def _schedule_reminders(session: AsyncSession, space: Space, owner_id: UUID) -> None:
    if space.event_date is None:
        return
    zone = ZoneInfo(space.timezone)
    for days_before in (await _get_settings(session, space.id)).reminder_days_before:
        local = datetime.combine(space.event_date - timedelta(days=days_before), time(9, 0))
        run_at = local.replace(tzinfo=zone).astimezone(timezone.utc)
        if run_at <= _utcnow() + timedelta(minutes=5):
            continue
        session.add(ScheduledEvent(
            space_id=space.id, user_id=owner_id, kind=ScheduledKind.reminder, run_at=run_at,
            timezone=space.timezone,
            payload={"space_id": str(space.id), "days_before": days_before},
            status=ScheduledStatus.scheduled, attempts=0,
            idempotency_key=f"space:{space.id}:reminder:{days_before}:v1",
        ))
    await session.flush()


async def _get_settings(session: AsyncSession, space_id: UUID) -> SpaceSettings:
    settings = await session.get(SpaceSettings, space_id)
    if settings is None:
        raise AppError("internal_error", "Space settings are missing.", 500)
    return settings


async def create_space(
    session: AsyncSession, owner: User, data: SpaceCreateIn, settings: Settings,
) -> tuple[Space, list[tuple[GuestAccessToken, str]]]:
    theme = await _get_theme_or_404(session, data.theme_id)
    await _require_theme_entitlement(session, owner.id, theme)
    visibility = _parse_enum(SpaceVisibility, data.visibility, "visibility")
    kind = _parse_enum(SpaceKind, data.kind, "kind")
    zone = require_timezone(data.timezone)
    publish_at = _as_utc(data.publish_at, zone) if data.publish_at else None
    if publish_at is not None and publish_at <= _utcnow():
        raise AppError("validation_error", "publish_at must be in the future.", 422)

    space = Space(
        owner_id=owner.id, title=data.title, description=data.description, kind=kind.value,
        occasion=data.occasion, theme_id=theme.id, visibility=visibility,
        contribution_policy=_parse_enum(ContributionPolicy, data.contribution_policy,
                                       "contribution_policy"),
        moderation_mode=_parse_enum(ModerationMode, data.moderation_mode, "moderation_mode"),
        allow_anonymous=data.allow_anonymous, allow_viewer_react=data.allow_viewer_react,
        ai_opt_in=data.ai_opt_in, event_date=data.event_date, publish_at=publish_at,
        location_label=data.location_label, timezone=zone, theme_overrides={},
        storage_quota_bytes=FREE_STORAGE_BYTES, storage_used_bytes=0,
    )
    session.add(space)
    await session.flush()
    session.add(SpaceSettings(
        space_id=space.id, reminder_enabled=True, reminder_days_before=[7, 1],
        digest_enabled=True, letter_delivery_timezone=owner.timezone or zone,
        default_reply_notify=True,
    ))
    minted = []
    for label, cap in (("General link", GuestRoleCap.contributor),
                       ("View-only link", GuestRoleCap.viewer)):
        minted.append(await _mint_token_row(session, space, owner.id, owner.email, label, cap))
    if publish_at is not None:
        await _schedule_reveal(session, space, publish_at)
    await _schedule_reminders(session, space, owner.id)
    await session.flush()
    return space, minted


async def update_space(
    session: AsyncSession, ctx: SpaceContext, data: SpacePatchIn,
) -> Space:
    from app.modules.permissions import capabilities as caps

    space = ctx.space
    changes = data.model_dump(exclude_unset=True)
    for field in changes:
        if not caps.can_edit_space_field(ctx, field):
            raise AppError("forbidden", f"You may not edit '{field}'.", 403)
    if "theme_id" in changes and changes["theme_id"] is not None:
        theme = await _get_theme_or_404(session, changes["theme_id"])
        await _require_theme_entitlement(session, space.owner_id, theme)
        space.theme_id = theme.id
    if "theme_overrides" in changes:
        space.theme_overrides = validate_theme_overrides(changes["theme_overrides"] or {})
    if "kind" in changes and changes["kind"] is not None:
        space.kind = _parse_enum(SpaceKind, changes["kind"], "kind").value
    if "visibility" in changes and changes["visibility"] is not None:
        space.visibility = _parse_enum(SpaceVisibility, changes["visibility"], "visibility")
    if "contribution_policy" in changes and changes["contribution_policy"] is not None:
        space.contribution_policy = _parse_enum(
            ContributionPolicy, changes["contribution_policy"], "contribution_policy")
    if "moderation_mode" in changes and changes["moderation_mode"] is not None:
        space.moderation_mode = _parse_enum(
            ModerationMode, changes["moderation_mode"], "moderation_mode")
    if "timezone" in changes and changes["timezone"] is not None:
        space.timezone = require_timezone(changes["timezone"])
    for field in ("title", "description", "occasion", "allow_anonymous", "allow_viewer_react",
                  "ai_opt_in", "event_date", "location_label", "cover_asset_id"):
        if field in changes:
            setattr(space, field, changes[field])
    if "publish_at" in changes:
        await _sync_reveal_event(session, space, changes["publish_at"])
    await session.flush()
    return space


async def _sync_reveal_event(
    session: AsyncSession, space: Space, publish_at: datetime | None
) -> None:
    active = await _active_reveal(session, space.id)
    if publish_at is None:
        space.publish_at = None
        if active is not None:
            await _cancel_event(session, active)
        return
    run_at = _as_utc(publish_at, space.timezone)
    if run_at <= _utcnow():
        # Publishing immediately: reveal now, no event needed.
        space.publish_at = None
        if space.visibility == SpaceVisibility.scheduled:
            space.visibility = SpaceVisibility.link
        if active is not None:
            await _cancel_event(session, active)
        return
    space.publish_at = run_at
    if active is not None:
        await _cancel_event(session, active)
    version = 1
    result = await session.execute(
        select(func.count()).select_from(ScheduledEvent).where(
            ScheduledEvent.space_id == space.id, ScheduledEvent.kind == ScheduledKind.reveal)
    )
    version = (result.scalar() or 0) + 1
    await _schedule_reveal(session, space, run_at, version=version)


async def delete_space(session: AsyncSession, ctx: SpaceContext) -> None:
    require_owner(ctx)
    ctx.space.deleted_at = _utcnow()
    await session.flush()


async def restore_space(session: AsyncSession, ctx: SpaceContext) -> None:
    require_owner(ctx)
    if ctx.space.deleted_at is None:
        raise AppError("conflict", "Space is not deleted.", 409)
    ctx.space.deleted_at = None
    await session.flush()


async def transfer_space(session: AsyncSession, ctx: SpaceContext, new_owner_id: UUID) -> None:
    require_owner(ctx)
    if new_owner_id == ctx.space.owner_id:
        raise AppError("conflict", "That user already owns this space.", 409)
    target = await session.get(User, new_owner_id)
    if target is None or target.deleted_at is not None:
        raise AppError("not_found", "New owner not found.", 404)
    old_owner_id = ctx.space.owner_id
    # Old owner stays on as collaborator; new owner sheds any membership.
    existing = await session.execute(
        select(SpaceMembership).where(SpaceMembership.space_id == ctx.space.id,
                                      SpaceMembership.user_id == old_owner_id)
    )
    row = existing.scalar_one_or_none()
    if row is None:
        session.add(SpaceMembership(space_id=ctx.space.id, user_id=old_owner_id,
                                    role=SpaceRole.collaborator, invited_by=new_owner_id))
    else:
        row.role = SpaceRole.collaborator
    victim = await session.execute(
        select(SpaceMembership).where(SpaceMembership.space_id == ctx.space.id,
                                      SpaceMembership.user_id == new_owner_id)
    )
    doomed = victim.scalar_one_or_none()
    if doomed is not None:
        await session.delete(doomed)
    ctx.space.owner_id = new_owner_id
    await session.flush()


async def list_member_rows(session: AsyncSession, ctx: SpaceContext) -> list[tuple]:
    from app.modules.permissions import capabilities as caps

    caps.require_staff(ctx)
    result = await session.execute(
        select(SpaceMembership, User)
        .join(User, User.id == SpaceMembership.user_id)
        .where(SpaceMembership.space_id == ctx.space.id)
        .order_by(SpaceMembership.created_at)
    )
    return list(result.all())


async def update_member_role(
    session: AsyncSession, ctx: SpaceContext, user_id: UUID, role: str
) -> SpaceMembership:
    from app.modules.permissions import capabilities as caps

    parsed = _parse_enum(SpaceRole, role, "role")
    if not caps.can_invite(ctx, parsed):
        raise AppError("forbidden", "You may not grant that role.", 403)
    result = await session.execute(
        select(SpaceMembership).where(SpaceMembership.space_id == ctx.space.id,
                                      SpaceMembership.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise AppError("not_found", "Membership not found.", 404)
    row.role = parsed
    await session.flush()
    return row


async def remove_member(session: AsyncSession, ctx: SpaceContext, user_id: UUID) -> None:
    from app.modules.permissions import capabilities as caps

    result = await session.execute(
        select(SpaceMembership).where(SpaceMembership.space_id == ctx.space.id,
                                      SpaceMembership.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise AppError("not_found", "Membership not found.", 404)
    leaving = ctx.user_id == user_id
    allowed = leaving or ctx.is_owner or (ctx.is_collaborator and row.role != SpaceRole.collaborator)
    if not allowed:
        raise AppError("forbidden", "You may not remove that member.", 403)
    await session.delete(row)
    await session.flush()


async def list_token_rows(session: AsyncSession, ctx: SpaceContext) -> list[GuestAccessToken]:
    from app.modules.permissions import capabilities as caps

    caps.require_staff(ctx)
    result = await session.execute(
        select(GuestAccessToken)
        .where(GuestAccessToken.space_id == ctx.space.id)
        .order_by(GuestAccessToken.created_at)
    )
    return list(result.scalars().all())


async def mint_token(
    session: AsyncSession, ctx: SpaceContext, label: str, role_cap: str,
    max_uses: int | None, expires_at: datetime | None,
) -> tuple[GuestAccessToken, str]:
    from app.modules.permissions import capabilities as caps

    caps.require_staff(ctx)
    cap = _parse_enum(GuestRoleCap, role_cap, "role_cap")
    if expires_at is not None:
        expires_at = _as_utc(expires_at, ctx.space.timezone)
        if expires_at <= _utcnow():
            raise AppError("validation_error", "expires_at must be in the future.", 422)
    email = ctx.actor.email if isinstance(ctx.actor, UserActor) else None
    return await _mint_token_row(session, ctx.space, ctx.user_id, email, label, cap,
                                 max_uses, expires_at)


async def revoke_token(session: AsyncSession, ctx: SpaceContext, token_id: UUID) -> None:
    from app.modules.permissions import capabilities as caps

    caps.require_staff(ctx)
    token = await session.get(GuestAccessToken, token_id)
    if token is None or token.space_id != ctx.space.id:
        raise AppError("not_found", "Token not found.", 404)
    token.revoked_at = _utcnow()
    await session.flush()


async def create_invitation(
    session: AsyncSession, ctx: SpaceContext, email: str, role: str, jobs: JobRunner,
    settings: Settings,
) -> Invitation:
    from email_validator import EmailNotValidError, validate_email

    from app.modules.permissions import capabilities as caps

    parsed = _parse_enum(SpaceRole, role, "role")
    if not caps.can_invite(ctx, parsed):
        raise AppError("forbidden", "You may not invite that role.", 403)
    try:
        normalized = validate_email(email.strip(), check_deliverability=False).normalized
    except EmailNotValidError:
        raise AppError("validation_error", "Invalid email address.", 422) from None
    raw = secrets.token_hex(32)
    invite = Invitation(
        space_id=ctx.space.id, email=normalized, role=parsed,
        token_hash=token_helpers.sha256_hex(raw), invited_by=ctx.user_id,
        expires_at=_utcnow() + timedelta(days=14),
    )
    session.add(invite)
    await session.flush()
    accept_url = f"{settings.frontend_base_url.rstrip('/')}/invite/{raw}"
    await jobs.enqueue(
        "send_email",
        {
            "to": normalized, "subject": f"You are invited to '{ctx.space.title}'",
            "template": "invite_v1",
            "text_body": (
                f"You have been invited to contribute to '{ctx.space.title}' on Memory Lane"
                f" as {parsed.value}.\n\nAccept here (single use, expires in 14 days):\n"
                f"{accept_url}\n"
            ),
        },
        idempotency_key=f"invite:{invite.id}",
    )
    return invite


async def preview_invitation(session: AsyncSession, raw_token: str) -> dict:
    invite = await _live_invitation(session, raw_token)
    space = await session.get(Space, invite.space_id)
    assert space is not None
    inviter = await session.get(User, invite.invited_by) if invite.invited_by else None
    return {
        "space_title": space.title,
        "role": invite.role.value,
        "inviter": inviter.display_name if inviter else None,
    }


async def _live_invitation(session: AsyncSession, raw_token: str) -> Invitation:
    result = await session.execute(
        select(Invitation).where(
            Invitation.token_hash == token_helpers.sha256_hex(raw_token.strip()))
    )
    invite = result.scalar_one_or_none()
    if invite is None or invite.revoked_at is not None or invite.expires_at <= _utcnow():
        raise AppError("gone", "This invitation is no longer valid.", 410)
    if invite.accepted_at is not None:
        raise AppError("conflict", "This invitation was already accepted.", 409)
    return invite


async def accept_invitation(
    session: AsyncSession, raw_token: str, user: User
) -> SpaceMembership:
    invite = await _live_invitation(session, raw_token)
    result = await session.execute(
        select(SpaceMembership).where(SpaceMembership.space_id == invite.space_id,
                                      SpaceMembership.user_id == user.id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = SpaceMembership(space_id=invite.space_id, user_id=user.id,
                              role=invite.role, invited_by=invite.invited_by)
        session.add(row)
    else:
        row.role = invite.role
    invite.accepted_at = _utcnow()
    await session.flush()
    return row


async def revoke_invitation(session: AsyncSession, ctx: SpaceContext, invite_id: UUID) -> None:
    from app.modules.permissions import capabilities as caps

    caps.require_staff(ctx)
    invite = await session.get(Invitation, invite_id)
    if invite is None or invite.space_id != ctx.space.id:
        raise AppError("not_found", "Invitation not found.", 404)
    invite.revoked_at = _utcnow()
    await session.flush()


async def request_purge(
    session: AsyncSession, ctx: SpaceContext, confirm_title: str, jobs: JobRunner,
) -> Archive:
    require_owner(ctx)
    if confirm_title != ctx.space.title:
        raise AppError("validation_error", "Confirmation title does not match.", 422)
    archive = Archive(
        space_id=ctx.space.id, requested_by=ctx.user_id, kind="purge",
        status="queued", idempotency_key=f"purge:{ctx.space.id}:{_utcnow().isoformat()}",
    )
    session.add(archive)
    await session.flush()
    await jobs.enqueue("purge_space", {"space_id": str(ctx.space.id),
                                      "archive_id": str(archive.id)},
                       idempotency_key=archive.idempotency_key)
    return archive


@job("purge_space")
async def purge_space_job(payload: dict) -> None:
    """Hard-delete a space: bytes first, then rows in dependency order."""
    from sqlalchemy import delete

    from app import db
    from app.models.ai import AIGeneratedAsset, AIGenerationJob
    from app.models.contributions import (
        Contribution,
        ContributionAttachment,
        MediaAsset,
        MediaProcessingJob,
    )
    from app.models.interactions import ModerationRecord, Reaction, Reply
    from app.models.scheduling import Notification, ScheduledEvent
    from app.services.storage import get_storage

    space_id = payload["space_id"]
    storage = get_storage()
    removed_files = 0
    removed_files += await storage.delete_prefix(f"originals/{space_id}")
    removed_files += await storage.delete_prefix(f"derivatives/{space_id}")

    async with db.session_scope() as session:
        contribution_ids = select(Contribution.id).where(Contribution.space_id == space_id)
        await session.execute(delete(ContributionAttachment).where(
            ContributionAttachment.contribution_id.in_(contribution_ids)))
        await session.execute(delete(Reaction).where(
            Reaction.contribution_id.in_(contribution_ids)))
        await session.execute(delete(Reply).where(
            Reply.contribution_id.in_(contribution_ids)))
        await session.execute(delete(ModerationRecord).where(
            ModerationRecord.space_id == space_id))
        await session.execute(delete(Contribution).where(Contribution.space_id == space_id))
        await session.execute(delete(MediaProcessingJob).where(
            MediaProcessingJob.asset_id.in_(select(MediaAsset.id).where(
                MediaAsset.space_id == space_id))))
        await session.execute(delete(MediaAsset).where(MediaAsset.space_id == space_id))
        await session.execute(delete(AIGeneratedAsset).where(AIGeneratedAsset.space_id == space_id))
        await session.execute(delete(AIGenerationJob).where(AIGenerationJob.space_id == space_id))
        await session.execute(delete(ScheduledEvent).where(ScheduledEvent.space_id == space_id))
        await session.execute(delete(Notification).where(Notification.space_id == space_id))
        await session.execute(delete(Archive).where(Archive.space_id == space_id))
        await session.execute(delete(GuestAccessToken).where(GuestAccessToken.space_id == space_id))
        await session.execute(delete(Invitation).where(Invitation.space_id == space_id))
        await session.execute(delete(SpaceMembership).where(SpaceMembership.space_id == space_id))
        await session.execute(delete(SpaceSettings).where(SpaceSettings.space_id == space_id))
        await session.execute(delete(Space).where(Space.id == space_id))
    logger.info("purged space=%s files=%d", space_id, removed_files)


async def my_role_label(ctx: SpaceContext) -> str | None:
    if ctx.is_owner:
        return "owner"
    if ctx.membership_role is not None:
        return ctx.membership_role.value
    if isinstance(ctx.actor, GuestActor) and ctx.token is not None:
        return f"guest:{ctx.token.role_cap.value}"
    return None


async def my_permissions(ctx: SpaceContext) -> list[str]:
    from app.modules.permissions import capabilities as caps

    names = ["view"]  # context load already enforced visibility
    if caps.can_post(ctx):
        names.append("post")
    if caps.can_react(ctx):
        names.append("react")
    if caps.can_reply(ctx):
        names.append("reply")
    if caps.can_moderate(ctx):
        names.append("moderate")
    if caps.can_edit_space(ctx):
        names.append("edit_space")
    if caps.can_manage_space(ctx):
        names.append("manage_space")
    if caps.can_run_ai(ctx):
        names.append("run_ai")
    if caps.can_export(ctx, "full_zip"):
        names.append("export")
    return names


async def list_spaces(
    session: AsyncSession, user_id: UUID, role_filter: str = "all",
    archived: bool = False,
) -> list[tuple[Space, str]]:
    """Spaces the user owns or belongs to, newest first.

    `archived=True` lists soft-deleted spaces awaiting restore-or-purge
    (owner's own only — members never see deleted spaces).
    """
    if role_filter not in ("all", "owner", "collaborator"):
        raise AppError("validation_error", "role must be all, owner, or collaborator.", 422)
    if archived:
        result = await session.execute(
            select(Space).where(Space.owner_id == user_id, Space.deleted_at.is_not(None))
            .order_by(Space.deleted_at.desc())
        )
        return [(space, "owner") for space in result.scalars().all()]
    owned: list[tuple[Space, str]] = []
    if role_filter in ("all", "owner"):
        result = await session.execute(
            select(Space).where(Space.owner_id == user_id, Space.deleted_at.is_(None))
            .order_by(Space.created_at.desc())
        )
        owned = [(space, "owner") for space in result.scalars().all()]
    membered: list[tuple[Space, str]] = []
    if role_filter in ("all", "collaborator"):
        result = await session.execute(
            select(Space, SpaceMembership.role)
            .join(SpaceMembership, SpaceMembership.space_id == Space.id)
            .where(SpaceMembership.user_id == user_id, Space.deleted_at.is_(None))
            .order_by(Space.created_at.desc())
        )
        membered = [(space, role.value) for space, role in result.all()
                    if not (role_filter == "collaborator" and role != SpaceRole.collaborator)]
    seen = {space.id for space, _ in owned}
    return owned + [(space, role) for space, role in membered if space.id not in seen]


def space_to_out(space: Space) -> dict:
    from app.modules.spaces.schemas import SpaceOut

    return SpaceOut(
        id=space.id, owner_id=space.owner_id, title=space.title, description=space.description,
        kind=space.kind, occasion=space.occasion, visibility=space.visibility.value,
        contribution_policy=space.contribution_policy.value,
        moderation_mode=space.moderation_mode.value,
        allow_anonymous=space.allow_anonymous, allow_viewer_react=space.allow_viewer_react,
        ai_opt_in=space.ai_opt_in, event_date=space.event_date, publish_at=space.publish_at,
        location_label=space.location_label, timezone=space.timezone,
        storage_quota_bytes=space.storage_quota_bytes, storage_used_bytes=space.storage_used_bytes,
        created_at=space.created_at, deleted_at=space.deleted_at,
    ).model_dump(mode="json")


async def space_detail(session: AsyncSession, ctx: SpaceContext) -> dict:
    from app.modules.spaces.schemas import ResolvedThemeOut, SpaceDetailOut, SpaceSettingsOut, ThemeOut

    space = ctx.space
    theme = await _get_theme_or_404(session, space.theme_id)
    entitled = theme.plan_required == Plan.free
    if not entitled and ctx.is_owner:
        entitled = await owner_plan(session, space.owner_id) == Plan.premium
    _, merged, customized = resolve_theme(space, theme)
    settings_row = await session.get(SpaceSettings, space.id)
    settings = None
    if settings_row is not None and ctx.is_staff:
        settings = SpaceSettingsOut(
            reminder_enabled=settings_row.reminder_enabled,
            reminder_days_before=settings_row.reminder_days_before,
            digest_enabled=settings_row.digest_enabled,
            letter_delivery_timezone=settings_row.letter_delivery_timezone,
            default_reply_notify=settings_row.default_reply_notify,
        )
    from datetime import datetime, timezone

    from app.models.enums import SpaceVisibility as Visibility

    now = datetime.now(timezone.utc)
    published = space.publish_at is not None and space.publish_at <= now
    preview = bool(ctx.is_staff and space.visibility == Visibility.scheduled and not published)
    detail = SpaceDetailOut(
        space=space_to_out(space),  # type: ignore[arg-type]
        theme=ResolvedThemeOut(
            theme=ThemeOut(
                id=theme.id, slug=theme.slug, name=theme.name, occasions=theme.occasions,
                tokens=theme.tokens, plan_required=theme.plan_required.value,
                entitled=entitled,
            ),
            tokens=merged, is_customized=customized,
        ),
        settings=settings,
        stats=await space_stats(session, ctx),
        my_role=await my_role_label(ctx),
        my_permissions=await my_permissions(ctx),
        preview=preview,
    )
    return detail.model_dump(mode="json")


async def space_stats(session: AsyncSession, ctx: SpaceContext) -> dict:
    """Actor-aware counts: staff see all rows, others see visible-only."""
    from sqlalchemy import String

    conditions = [Contribution.space_id == ctx.space.id, Contribution.deleted_at.is_(None)]
    if not ctx.is_staff:
        conditions.append(Contribution.status == ContributionStatus.visible)
        conditions.append(Contribution.is_private_to_owner.is_(False))
    total = await session.scalar(select(func.count()).select_from(Contribution).where(*conditions))
    media = await session.scalar(
        select(func.count()).select_from(MediaAsset).where(
            MediaAsset.space_id == ctx.space.id, MediaAsset.deleted_at.is_(None),
            MediaAsset.status == "ready",
        )
    )
    contributors = await session.scalar(
        select(func.count(func.distinct(func.coalesce(
            Contribution.author_user_id.cast(String),
            Contribution.guest_token_id.cast(String),
            Contribution.guest_name,
        )))).select_from(Contribution).where(*conditions)
    )
    return {"contributions": total or 0, "media": media or 0, "contributors": contributors or 0}


