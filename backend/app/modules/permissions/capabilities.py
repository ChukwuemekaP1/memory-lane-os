"""Space capabilities: the single server-side enforcement point (ADR-006).

Every space-scoped route loads a SpaceContext (which itself enforces
visibility) and then asks capability predicates. Frontend hiding is cosmetic;
these checks run on every request. Semantics follow PERMISSIONS_MATRIX.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.logging import get_logger
from app.models.contributions import Contribution
from app.models.enums import (
    ContributionPolicy,
    ContributionStatus,
    GuestRoleCap,
    SpaceRole,
    SpaceVisibility,
)
from app.models.spaces import GuestAccessToken, Space, SpaceMembership
from app.modules.permissions.actor import Actor, GuestActor, UserActor

logger = get_logger(__name__)

NOT_FOUND = AppError("not_found", "Space not found.", 404)
FORBIDDEN = AppError("forbidden", "You do not have permission for this action.", 403)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class SpaceContext:
    space: Space
    actor: Actor | None
    membership_role: SpaceRole | None = None
    token: GuestAccessToken | None = None
    via_admin: bool = False

    @property
    def is_owner(self) -> bool:
        return (
            isinstance(self.actor, UserActor)
            and self.actor.user_id == self.space.owner_id
        )

    @property
    def is_collaborator(self) -> bool:
        return self.membership_role == SpaceRole.collaborator

    @property
    def is_staff(self) -> bool:
        return self.is_owner or self.is_collaborator or self.via_admin

    @property
    def user_id(self) -> UUID | None:
        if isinstance(self.actor, UserActor):
            return self.actor.user_id
        return None

    @property
    def guest_token_id(self) -> UUID | None:
        if isinstance(self.actor, GuestActor):
            return self.actor.token_id
        return None


def _published(space: Space) -> bool:
    return (
        space.visibility != SpaceVisibility.scheduled
        or (space.publish_at is not None and space.publish_at <= _utcnow())
    )


async def load_space_context(
    session: AsyncSession, actor: Actor | None, space_id: UUID,
    *, include_deleted_owner: bool = True,
) -> SpaceContext:
    """Load the space + actor relationship, enforcing visibility.

    Raises 404 for invisible/missing spaces (no oracle), 401 is the caller's
    job when no credential fits (see require_* guards below).
    """
    space = await session.get(Space, space_id)
    if space is None:
        raise NOT_FOUND
    if space.deleted_at is not None:
        if not (
            include_deleted_owner
            and isinstance(actor, UserActor)
            and actor.user_id == space.owner_id
        ):
            raise NOT_FOUND

    # Owner always passes (even pre-publish / private / deleted-for-restore).
    if isinstance(actor, UserActor) and actor.user_id == space.owner_id:
        return SpaceContext(space=space, actor=actor)

    # Admin support access: read-bypass, audit-logged. Mutations stay gated.
    if isinstance(actor, UserActor) and actor.is_admin:
        from app.models.audit import AuditEvent

        logger.info("admin space access user=%s space=%s", actor.user_id, space.id)
        session.add(AuditEvent(actor_user_id=actor.user_id, action="admin.space.read",
                               space_id=space.id, meta={}))
        await session.flush()
        return SpaceContext(space=space, actor=actor, via_admin=True)

    membership_role: SpaceRole | None = None
    if isinstance(actor, UserActor):
        result = await session.execute(
            select(SpaceMembership.role).where(
                SpaceMembership.space_id == space.id,
                SpaceMembership.user_id == actor.user_id,
            )
        )
        membership_role = result.scalar_one_or_none()

    token: GuestAccessToken | None = None
    if isinstance(actor, GuestActor):
        if actor.space_id != space.id:
            raise NOT_FOUND  # tokens never cross spaces
        token = await session.get(GuestAccessToken, actor.token_id)
        if token is None or token.revoked_at is not None:
            raise AppError("gone", "This invite link is no longer valid.", 410)

    visibility = space.visibility
    if visibility == SpaceVisibility.public:
        pass  # reads open; writes stay credentialed (checked per capability)
    elif visibility == SpaceVisibility.private:
        if membership_role is None:
            raise NOT_FOUND  # tokens grant nothing on private spaces
    elif visibility == SpaceVisibility.scheduled and not _published(space):
        # Staff-only preview is handled by the owner/admin early-returns;
        # collaborators preview too, everyone else 404s.
        if membership_role != SpaceRole.collaborator:
            raise NOT_FOUND
    else:  # link, or scheduled+published
        if membership_role is None and token is None:
            raise NOT_FOUND

    return SpaceContext(space=space, actor=actor, membership_role=membership_role,
                        token=token)


def _credential_class(ctx: SpaceContext) -> str:
    """One of: owner, collaborator, member, guest_contributor, guest_viewer, none."""
    if ctx.is_owner:
        return "owner"
    if ctx.is_collaborator:
        return "collaborator"
    if isinstance(ctx.actor, UserActor):
        return "member" if ctx.membership_role is not None else "none"
    if isinstance(ctx.actor, GuestActor) and ctx.token is not None:
        return (
            "guest_contributor"
            if ctx.token.role_cap == GuestRoleCap.contributor
            else "guest_viewer"
        )
    return "none"


def can_post(ctx: SpaceContext) -> bool:
    """Contribution/upload/reply permission: credential ∩ space policy."""
    if ctx.is_owner or ctx.is_collaborator:
        return True
    policy = ctx.space.contribution_policy
    if policy == ContributionPolicy.owner_only:
        return False
    cred = _credential_class(ctx)
    if policy == ContributionPolicy.members:
        return cred == "member"
    if policy == ContributionPolicy.link_contributors:
        return cred in ("member", "guest_contributor")
    # anyone_with_link: viewer-cap tokens may post as well.
    return cred in ("member", "guest_contributor", "guest_viewer")


def can_react(ctx: SpaceContext) -> bool:
    if ctx.is_staff:
        return True
    cred = _credential_class(ctx)
    if cred in ("member", "guest_contributor"):
        return True
    return cred == "guest_viewer" and bool(ctx.space.allow_viewer_react)


def can_reply(ctx: SpaceContext) -> bool:
    # Replies follow posting rights (anyone who may post may reply).
    return can_post(ctx)


def can_edit_space(ctx: SpaceContext) -> bool:
    return bool(ctx.is_owner or ctx.is_collaborator)


def can_edit_space_field(ctx: SpaceContext, field: str) -> bool:
    if ctx.is_owner:
        return True
    if not ctx.is_collaborator:
        return False
    return field in {"title", "description", "event_date", "location_label", "cover_asset_id"}


def can_manage_space(ctx: SpaceContext) -> bool:
    """Privacy, policy, tokens, members-admin, delete, transfer, purge."""
    return ctx.is_owner


def can_invite(ctx: SpaceContext, role: SpaceRole) -> bool:
    if ctx.is_owner:
        return True
    return ctx.is_collaborator and role != SpaceRole.collaborator


def can_moderate(ctx: SpaceContext) -> bool:
    return bool(ctx.is_staff)


def can_run_ai(ctx: SpaceContext) -> bool:
    if not (ctx.is_owner or ctx.is_collaborator):
        return False
    return bool(ctx.space.ai_opt_in)


def can_schedule(ctx: SpaceContext) -> bool:
    return bool(ctx.is_owner or ctx.is_collaborator)


def can_export(ctx: SpaceContext, kind: str) -> bool:
    if ctx.is_owner:
        return True
    if ctx.is_collaborator:
        return kind in ("full_zip", "data_export")
    return False


def can_view_item(ctx: SpaceContext, item: Contribution) -> bool:
    if ctx.is_owner or ctx.via_admin:
        return True
    if item.is_private_to_owner:
        return is_author(ctx, item)
    if item.status == ContributionStatus.visible:
        return True
    if ctx.is_collaborator:
        return True  # staff sees pending/hidden/rejected (never private)
    return is_author(ctx, item)  # authors see their own pending/rejected


def can_edit_item(ctx: SpaceContext, item: Contribution) -> bool:
    if not is_author(ctx, item):
        return False  # moderators hide, never edit others' items
    if ctx.is_owner or ctx.is_collaborator:
        return True
    window = timedelta(minutes=15) if isinstance(ctx.actor, GuestActor) else timedelta(hours=24)
    created = item.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return _utcnow() - created <= window


def can_delete_item(ctx: SpaceContext, item: Contribution) -> bool:
    return bool(ctx.is_staff or is_author(ctx, item))


def can_view_original(ctx: SpaceContext, uploader_user_id: UUID | None,
                      uploader_token_id: UUID | None) -> bool:
    if ctx.is_staff:
        return True
    if ctx.user_id is not None and uploader_user_id == ctx.user_id:
        return True
    return ctx.guest_token_id is not None and uploader_token_id == ctx.guest_token_id


def is_author(ctx: SpaceContext, item: Contribution) -> bool:
    if ctx.user_id is not None and item.author_user_id == ctx.user_id:
        return True
    return ctx.guest_token_id is not None and item.guest_token_id == ctx.guest_token_id


def display_name(ctx: SpaceContext, item: Contribution) -> str | None:
    """Author display name honoring anonymity (None = anonymous)."""
    if item.is_anonymous and not ctx.is_staff:
        return None
    return item.guest_name or item.author_snapshot


def require_post(ctx: SpaceContext) -> None:
    if not can_post(ctx):
        if ctx.actor is None:
            raise AppError("unauthenticated", "Authentication required.", 401)
        raise AppError("forbidden", "This space is not accepting your contributions.", 403)


def require_staff(ctx: SpaceContext) -> None:
    if not ctx.is_staff:
        if ctx.actor is None:
            raise AppError("unauthenticated", "Authentication required.", 401)
        raise FORBIDDEN


def require_owner(ctx: SpaceContext) -> None:
    if not ctx.is_owner:
        if ctx.actor is None:
            raise AppError("unauthenticated", "Authentication required.", 401)
        raise FORBIDDEN

