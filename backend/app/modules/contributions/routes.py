"""Contribution routes: posting, feeds, reactions, replies, moderation."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import enforce_rate_limit, get_job_runner_dep, get_rate_limiter_dep
from app.errors import ok_payload
from app.modules.contributions import service
from app.modules.contributions.schemas import (
    ContributionCreateIn,
    ContributionPatchIn,
    ModerationActionIn,
    ReactionIn,
    ReplyCreateIn,
    ReportIn,
    TagCreateIn,
)
from app.modules.permissions.actor import get_actor
from app.modules.permissions.capabilities import SpaceContext, load_space_context
from app.pagination import page_payload
from app.services.jobs import JobRunner
from app.services.ratelimit import RateLimiter

router = APIRouter(tags=["contributions"])


async def _ctx(
    space_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SpaceContext:
    actor = await get_actor(request, session)
    return await load_space_context(session, actor, space_id)

SpaceCtx = Annotated[SpaceContext, Depends(_ctx)]


def _actor_key(ctx: SpaceContext, request: Request) -> str:
    ip = request.client.host if request.client else "unknown"
    if ctx.user_id is not None:
        return f"user:{ctx.user_id}:{ip}"
    if ctx.guest_token_id is not None:
        return f"token:{ctx.guest_token_id}:{ip}"
    return f"anon:{ip}"


@router.post("/spaces/{space_id}/contributions", status_code=status.HTTP_201_CREATED)
async def post_contribution(
    body: ContributionCreateIn,
    ctx: SpaceCtx,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter_dep)],
) -> Response:
    from fastapi.responses import JSONResponse

    from app.logging import request_id_ctx

    await enforce_rate_limit(limiter, f"post:{ctx.space.id}:{_actor_key(ctx, request)}", 30, 60)
    item, replayed = await service.create_contribution(
        session, ctx, kind=body.kind, body=body.body,
        guest_name=body.guest_name, is_anonymous=body.is_anonymous,
        is_private_to_owner=body.is_private_to_owner, taken_at=body.taken_at,
        asset_ids=body.asset_ids,
        idempotency_key=request.headers.get("idempotency-key"),
    )
    detail = await service.contribution_detail(session, ctx, item.id)
    payload = {"data": detail, "request_id": request_id_ctx.get()}
    headers = {"Idempotent-Replayed": "true"} if replayed else None
    if replayed:
        status_code = 200
    elif detail["status"] == "pending":
        status_code = 202
    else:
        status_code = 201
    return JSONResponse(status_code=status_code, content=payload, headers=headers)


@router.get("/spaces/{space_id}/contributions")
async def list_space_contributions(
    ctx: SpaceCtx,
    session: Annotated[AsyncSession, Depends(get_session)],
    kind: str | None = None,
    q: str | None = Query(default=None, max_length=200),
    taken_from: datetime | None = None,
    taken_to: datetime | None = None,
    author: str | None = Query(default=None, max_length=80),
    sort: str = "-created_at",
    cursor: str | None = None,
    limit: int | None = Query(default=None, ge=1, le=100),
) -> dict:
    rows, next_cursor = await service.list_contributions(
        session, ctx, kind, q, taken_from, taken_to, author, sort, cursor, limit)
    cards = [await service.contribution_card(session, ctx, item) for item in rows]
    return page_payload(cards, next_cursor)


@router.get("/contributions/{item_id}")
async def get_contribution(
    item_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    from app.models.contributions import Contribution

    from app.errors import AppError

    item = await session.get(Contribution, item_id)
    if item is None:
        raise AppError("not_found", "Contribution not found.", 404)
    actor = await get_actor(request, session)
    ctx = await load_space_context(session, actor, item.space_id)
    return ok_payload(await service.contribution_detail(session, ctx, item_id))


@router.patch("/contributions/{item_id}")
async def patch_contribution(
    item_id: UUID,
    body: ContributionPatchIn,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    from app.models.contributions import Contribution

    from app.errors import AppError

    item = await session.get(Contribution, item_id)
    if item is None:
        raise AppError("not_found", "Contribution not found.", 404)
    actor = await get_actor(request, session)
    ctx = await load_space_context(session, actor, item.space_id)
    await service.patch_contribution(session, ctx, item_id, body.body, body.taken_at)
    return ok_payload(await service.contribution_detail(session, ctx, item_id))


@router.delete("/contributions/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contribution(
    item_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    from app.models.contributions import Contribution

    from app.errors import AppError

    item = await session.get(Contribution, item_id)
    if item is None:
        raise AppError("not_found", "Contribution not found.", 404)
    actor = await get_actor(request, session)
    ctx = await load_space_context(session, actor, item.space_id)
    await service.delete_contribution(session, ctx, item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/contributions/{item_id}/reactions", status_code=status.HTTP_201_CREATED)
async def add_reaction(
    item_id: UUID,
    body: ReactionIn,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter_dep)],
) -> Response:
    from fastapi.responses import JSONResponse

    from app.logging import request_id_ctx
    from app.models.contributions import Contribution

    from app.errors import AppError

    item = await session.get(Contribution, item_id)
    if item is None:
        raise AppError("not_found", "Contribution not found.", 404)
    actor = await get_actor(request, session)
    ctx = await load_space_context(session, actor, item.space_id)
    await enforce_rate_limit(limiter, f"react:{ctx.space.id}:{_actor_key(ctx, request)}", 60, 60)
    created = await service.toggle_reaction(session, ctx, item_id, body.emoji, True)
    if not created:
        return JSONResponse(status_code=204, content=None)
    detail = await service.contribution_detail(session, ctx, item_id)
    payload = {"data": {"reactions": detail["reactions"]}, "request_id": request_id_ctx.get()}
    return JSONResponse(status_code=201, content=payload)


@router.delete("/contributions/{item_id}/reactions/{emoji}",
               status_code=status.HTTP_204_NO_CONTENT)
async def remove_reaction(
    item_id: UUID,
    emoji: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    from app.models.contributions import Contribution

    from app.errors import AppError

    item = await session.get(Contribution, item_id)
    if item is None:
        raise AppError("not_found", "Contribution not found.", 404)
    actor = await get_actor(request, session)
    ctx = await load_space_context(session, actor, item.space_id)
    await service.toggle_reaction(session, ctx, item_id, emoji, False)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/contributions/{item_id}/replies")
async def list_replies(
    item_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    from app.models.contributions import Contribution

    from app.errors import AppError

    item = await session.get(Contribution, item_id)
    if item is None:
        raise AppError("not_found", "Contribution not found.", 404)
    actor = await get_actor(request, session)
    ctx = await load_space_context(session, actor, item.space_id)
    return ok_payload(await service.list_replies(session, ctx, item_id))


@router.post("/contributions/{item_id}/replies", status_code=status.HTTP_201_CREATED)
async def post_reply(
    item_id: UUID,
    body: ReplyCreateIn,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter_dep)],
) -> dict:
    from app.models.contributions import Contribution

    from app.errors import AppError

    item = await session.get(Contribution, item_id)
    if item is None:
        raise AppError("not_found", "Contribution not found.", 404)
    actor = await get_actor(request, session)
    ctx = await load_space_context(session, actor, item.space_id)
    await enforce_rate_limit(limiter, f"reply:{ctx.space.id}:{_actor_key(ctx, request)}", 60, 60)
    reply = await service.create_reply(session, ctx, item_id, body.body, body.guest_name)
    return ok_payload({"id": str(reply.id)})


@router.delete("/replies/{reply_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reply(
    reply_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    from app.models.contributions import Contribution
    from app.models.interactions import Reply

    from app.errors import AppError

    reply = await session.get(Reply, reply_id)
    if reply is None:
        raise AppError("not_found", "Reply not found.", 404)
    parent = await session.get(Contribution, reply.contribution_id)
    if parent is None:
        raise AppError("not_found", "Reply not found.", 404)
    actor = await get_actor(request, session)
    ctx = await load_space_context(session, actor, parent.space_id)
    await service.delete_reply(session, ctx, reply_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/contributions/{item_id}/report", status_code=status.HTTP_202_ACCEPTED)
async def report_item(
    item_id: UUID,
    body: ReportIn,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter_dep)],
    jobs: Annotated[JobRunner, Depends(get_job_runner_dep)],
) -> dict:
    from app.models.contributions import Contribution

    from app.errors import AppError

    item = await session.get(Contribution, item_id)
    if item is None:
        raise AppError("not_found", "Contribution not found.", 404)
    actor = await get_actor(request, session)
    ctx = await load_space_context(session, actor, item.space_id)
    await enforce_rate_limit(limiter, f"report:{ctx.space.id}:{_actor_key(ctx, request)}", 10, 60)
    await service.report_contribution(session, ctx, item_id, body.reason, jobs)
    return ok_payload({"reported": True})


@router.post("/contributions/{item_id}/tags", status_code=status.HTTP_201_CREATED)
async def suggest_tag(
    item_id: UUID,
    body: TagCreateIn,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    from app.models.contributions import Contribution

    from app.errors import AppError

    item = await session.get(Contribution, item_id)
    if item is None:
        raise AppError("not_found", "Contribution not found.", 404)
    actor = await get_actor(request, session)
    ctx = await load_space_context(session, actor, item.space_id)
    return ok_payload(await service.suggest_tag(session, ctx, item_id, body.label, body.user_id))


@router.get("/contributions/{item_id}/tags")
async def list_tags(
    item_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    from app.models.contributions import Contribution

    from app.errors import AppError

    item = await session.get(Contribution, item_id)
    if item is None:
        raise AppError("not_found", "Contribution not found.", 404)
    actor = await get_actor(request, session)
    ctx = await load_space_context(session, actor, item.space_id)
    return ok_payload(await service.list_tags(session, ctx, item_id))


async def _tag_ctx(tag_id: UUID, request: Request, session: AsyncSession):  # type: ignore[no-untyped-def]
    from app.models.contributions import Contribution
    from app.models.interactions import ContributionTag

    from app.errors import AppError

    tag = await session.get(ContributionTag, tag_id)
    if tag is None:
        raise AppError("not_found", "Tag not found.", 404)
    parent = await session.get(Contribution, tag.contribution_id)
    if parent is None:
        raise AppError("not_found", "Tag not found.", 404)
    actor = await get_actor(request, session)
    ctx = await load_space_context(session, actor, parent.space_id)
    return ctx


@router.post("/tags/{tag_id}/approve")
async def approve_tag(
    tag_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    ctx = await _tag_ctx(tag_id, request, session)
    return ok_payload(await service.decide_tag(session, ctx, tag_id, True))


@router.post("/tags/{tag_id}/decline")
async def decline_tag(
    tag_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    ctx = await _tag_ctx(tag_id, request, session)
    return ok_payload(await service.decide_tag(session, ctx, tag_id, False))


@router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    ctx = await _tag_ctx(tag_id, request, session)
    await service.delete_tag(session, ctx, tag_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/spaces/{space_id}/moderation/queue")
async def moderation_queue(
    ctx: SpaceCtx,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    return ok_payload(await service.moderation_queue(session, ctx))


@router.get("/spaces/{space_id}/moderation/log")
async def moderation_log(
    ctx: SpaceCtx,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    return ok_payload(await service.moderation_log(session, ctx))


@router.post("/moderation/{target_type}/{target_id}/{action}")
async def moderate_item(
    target_type: str,
    target_id: UUID,
    action: str,
    body: ModerationActionIn,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    jobs: Annotated[JobRunner, Depends(get_job_runner_dep)],
) -> dict:
    from app.models.contributions import Contribution
    from app.models.interactions import Reply

    from app.errors import AppError

    space_id: UUID | None = None
    if target_type == "contribution":
        item = await session.get(Contribution, target_id)
        space_id = item.space_id if item is not None else None
    elif target_type == "reply":
        reply = await session.get(Reply, target_id)
        if reply is not None:
            parent = await session.get(Contribution, reply.contribution_id)
            space_id = parent.space_id if parent is not None else None
    if space_id is None:
        raise AppError("not_found", "Target not found.", 404)
    actor = await get_actor(request, session)
    ctx = await load_space_context(session, actor, space_id)
    return ok_payload(await service.moderate(session, ctx, target_type, target_id, action,
                                             body.reason, jobs))
