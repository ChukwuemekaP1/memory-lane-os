"""Spaces routes: CRUD, settings, members, tokens, invitations (spec §7-8)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import SettingsDep, get_job_runner_dep
from app.errors import AppError, ok_payload
from app.models.users import User
from app.modules.permissions.actor import UserActor, get_actor, require_user
from app.modules.permissions.capabilities import SpaceContext, load_space_context
from app.modules.spaces import service
from app.modules.spaces.schemas import (
    GuestTokenMintIn,
    GuestTokenMintOut,
    GuestTokenOut,
    InvitationCreateIn,
    InvitationOut,
    MembershipOut,
    MembershipPatchIn,
    PurgeIn,
    SpaceCreateIn,
    SpacePatchIn,
    SpaceSettingsOut,
    SpaceSettingsPatchIn,
    ThemeOut,
    ThemePreviewIn,
    TransferIn,
)
from app.services.jobs import JobRunner

router = APIRouter(tags=["spaces"])


async def _ctx(
    space_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SpaceContext:
    actor = await get_actor(request, session)
    return await load_space_context(session, actor, space_id)

SpaceCtx = Annotated[SpaceContext, Depends(_ctx)]


def _token_out(token) -> dict:  # type: ignore[no-untyped-def]
    return GuestTokenOut(
        id=token.id, label=token.label, role_cap=token.role_cap.value,
        use_count=token.use_count, max_uses=token.max_uses, expires_at=token.expires_at,
        revoked_at=token.revoked_at, created_at=token.created_at,
    ).model_dump(mode="json")


@router.post("/spaces", status_code=status.HTTP_201_CREATED)
async def create_space(
    body: SpaceCreateIn,
    settings: SettingsDep,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[UserActor, Depends(require_user)],
) -> dict:
    owner = await session.get(User, user.user_id)
    assert owner is not None
    space, minted = await service.create_space(session, owner, body, settings)
    links = [
        GuestTokenMintOut(
            token=_token_out(token),  # type: ignore[arg-type]
            url=service.guest_url(space.id, raw, settings),
            qr_payload=service.guest_url(space.id, raw, settings),
            token_preview=raw[:8],
        ).model_dump(mode="json")
        for token, raw in minted
    ]
    return ok_payload({"space": service.space_to_out(space), "guest_links": links})


@router.get("/spaces")
async def list_spaces(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[UserActor, Depends(require_user)],
    role: str = Query(default="all"),
    archived: bool = Query(default=False),
) -> dict:
    rows = await service.list_spaces(session, user.user_id, role, archived)
    return ok_payload([
        {"space": service.space_to_out(space), "my_role": label} for space, label in rows
    ])


@router.get("/spaces/{space_id}")
async def get_space(
    ctx: SpaceCtx,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    return ok_payload(await service.space_detail(session, ctx))


@router.patch("/spaces/{space_id}")
async def patch_space(
    body: SpacePatchIn,
    ctx: SpaceCtx,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    await service.update_space(session, ctx, body)
    return ok_payload(await service.space_detail(session, ctx))


@router.delete("/spaces/{space_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_space(
    ctx: SpaceCtx,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    await service.delete_space(session, ctx)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/spaces/{space_id}/restore")
async def restore_space(
    ctx: SpaceCtx,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    await service.restore_space(session, ctx)
    return ok_payload(await service.space_detail(session, ctx))


@router.post("/spaces/{space_id}/purge", status_code=status.HTTP_202_ACCEPTED)
async def purge_space(
    body: PurgeIn,
    ctx: SpaceCtx,
    session: Annotated[AsyncSession, Depends(get_session)],
    jobs: Annotated[JobRunner, Depends(get_job_runner_dep)],
) -> dict:
    archive = await service.request_purge(session, ctx, body.confirm_title, jobs)
    return ok_payload({"purge_archive_id": str(archive.id)})


@router.post("/spaces/{space_id}/transfer")
async def transfer_space(
    body: TransferIn,
    ctx: SpaceCtx,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    await service.transfer_space(session, ctx, body.new_owner_user_id)
    return ok_payload(await service.space_detail(session, ctx))


@router.get("/spaces/{space_id}/settings")
async def get_settings_route(
    ctx: SpaceCtx,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    from app.models.spaces import SpaceSettings

    if not ctx.is_staff:
        raise AppError("forbidden", "Staff only.", 403)
    row = await session.get(SpaceSettings, ctx.space.id)
    assert row is not None
    return ok_payload(SpaceSettingsOut(
        reminder_enabled=row.reminder_enabled, reminder_days_before=row.reminder_days_before,
        digest_enabled=row.digest_enabled, letter_delivery_timezone=row.letter_delivery_timezone,
        default_reply_notify=row.default_reply_notify,
    ).model_dump(mode="json"))


@router.patch("/spaces/{space_id}/settings")
async def patch_settings(
    body: SpaceSettingsPatchIn,
    ctx: SpaceCtx,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    from app.models.spaces import SpaceSettings

    if not ctx.is_staff:
        raise AppError("forbidden", "Staff only.", 403)
    row = await session.get(SpaceSettings, ctx.space.id)
    assert row is not None
    changes = body.model_dump(exclude_unset=True)
    if "reminder_days_before" in changes and changes["reminder_days_before"] is not None:
        days = changes["reminder_days_before"]
        if not days or len(days) > 5 or any(not isinstance(d, int) or d < 0 or d > 365 for d in days):
            raise AppError("validation_error", "reminder_days_before must be 1-5 days 0-365.", 422)
    if "letter_delivery_timezone" in changes and changes["letter_delivery_timezone"] is not None:
        service.require_timezone(changes["letter_delivery_timezone"])
    for field, value in changes.items():
        if value is not None:
            setattr(row, field, value)
    await session.flush()
    return await get_settings_route(ctx, session)


@router.get("/spaces/{space_id}/guest-tokens")
async def list_guest_tokens(
    ctx: SpaceCtx,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    rows = await service.list_token_rows(session, ctx)
    return ok_payload([_token_out(token) for token in rows])


@router.post("/spaces/{space_id}/guest-tokens", status_code=status.HTTP_201_CREATED)
async def mint_guest_token(
    body: GuestTokenMintIn,
    ctx: SpaceCtx,
    settings: SettingsDep,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    token, raw = await service.mint_token(
        session, ctx, body.label, body.role_cap, body.max_uses, body.expires_at)
    url = service.guest_url(ctx.space.id, raw, settings)
    return ok_payload(GuestTokenMintOut(
        token=_token_out(token),  # type: ignore[arg-type]
        url=url, qr_payload=url, token_preview=raw[:8],
    ).model_dump(mode="json"))


@router.post("/guest-tokens/{token_id}/revoke")
async def revoke_guest_token(
    token_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    from app.models.spaces import GuestAccessToken

    token = await session.get(GuestAccessToken, token_id)
    if token is None:
        raise AppError("not_found", "Token not found.", 404)
    actor = await get_actor(request, session)
    ctx = await load_space_context(session, actor, token.space_id)
    await service.revoke_token(session, ctx, token_id)
    return ok_payload({"revoked_at": _token_out(token)["revoked_at"]})


@router.get("/spaces/{space_id}/members")
async def list_members(
    ctx: SpaceCtx,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    rows = await service.list_member_rows(session, ctx)
    return ok_payload([
        MembershipOut(
            user_id=membership.user_id, email=user.email, display_name=user.display_name,
            role=membership.role.value, created_at=membership.created_at,
        ).model_dump(mode="json")
        for membership, user in rows
    ])


@router.patch("/spaces/{space_id}/members/{user_id}")
async def patch_member(
    user_id: UUID,
    body: MembershipPatchIn,
    ctx: SpaceCtx,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    row = await service.update_member_role(session, ctx, user_id, body.role)
    user = await session.get(User, user_id)
    assert user is not None
    return ok_payload(MembershipOut(
        user_id=row.user_id, email=user.email, display_name=user.display_name,
        role=row.role.value, created_at=row.created_at,
    ).model_dump(mode="json"))


@router.delete("/spaces/{space_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_member(
    user_id: UUID,
    ctx: SpaceCtx,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    await service.remove_member(session, ctx, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/spaces/{space_id}/invitations", status_code=status.HTTP_202_ACCEPTED)
async def create_invitation(
    body: InvitationCreateIn,
    ctx: SpaceCtx,
    settings: SettingsDep,
    session: Annotated[AsyncSession, Depends(get_session)],
    jobs: Annotated[JobRunner, Depends(get_job_runner_dep)],
) -> dict:
    invite = await service.create_invitation(session, ctx, body.email, body.role, jobs, settings)
    return ok_payload(InvitationOut(
        id=invite.id, email=invite.email, role=invite.role.value,
        accepted_at=invite.accepted_at, expires_at=invite.expires_at,
        revoked_at=invite.revoked_at, created_at=invite.created_at,
    ).model_dump(mode="json"))


@router.get("/invitations/{token}")
async def preview_invitation(
    token: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    return ok_payload(await service.preview_invitation(session, token))


@router.post("/invitations/{token}/accept")
async def accept_invitation(
    token: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[UserActor, Depends(require_user)],
) -> dict:
    account = await session.get(User, user.user_id)
    assert account is not None
    row = await service.accept_invitation(session, token, account)
    return ok_payload({"space_id": str(row.space_id), "role": row.role.value})


@router.post("/invitations/{invite_id}/revoke")
async def revoke_invitation(
    invite_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    from app.models.spaces import Invitation

    invite = await session.get(Invitation, invite_id)
    if invite is None:
        raise AppError("not_found", "Invitation not found.", 404)
    actor = await get_actor(request, session)
    ctx = await load_space_context(session, actor, invite.space_id)
    await service.revoke_invitation(session, ctx, invite_id)
    return ok_payload({"revoked": True})


@router.post("/spaces/{space_id}/theme-preview")
async def preview_theme_route(
    body: ThemePreviewIn,
    ctx: SpaceCtx,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    return ok_payload(await service.preview_theme(
        session, ctx, body.theme_id, body.overrides))


@router.get("/themes")
async def list_themes(
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[object, Depends(get_actor)],
    occasion: str | None = None,
) -> dict:
    from sqlalchemy import select

    from app.models.enums import Plan
    from app.models.spaces import Theme

    result = await session.execute(
        select(Theme).where(Theme.is_active.is_(True)).order_by(Theme.name)
    )
    themes = list(result.scalars().all())
    if occasion:
        themes = [t for t in themes if occasion in t.occasions]
    plan = Plan.free
    if isinstance(actor, UserActor):
        plan = await service.owner_plan(session, actor.user_id)
    return ok_payload([
        ThemeOut(
            id=theme.id, slug=theme.slug, name=theme.name, occasions=theme.occasions,
            tokens=theme.tokens, plan_required=theme.plan_required.value,
            entitled=(theme.plan_required == Plan.free or plan == Plan.premium),
        ).model_dump(mode="json")
        for theme in themes
    ])
