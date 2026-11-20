"""Archive routes: exports, downloads, share links, preservation."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import get_job_runner_dep
from app.errors import AppError, ok_payload
from app.modules.archives import jobs as _jobs  # noqa: F401 (registers build_archive/purge_user)
from app.modules.archives import service
from app.modules.archives.schemas import ArchiveCreateIn, CloseAccountIn, PurgeAccountIn
from app.modules.permissions.actor import UserActor, get_actor, require_user
from app.modules.permissions.capabilities import SpaceContext, load_space_context
from app.services.jobs import JobRunner

router = APIRouter(tags=["archives"])


async def _ctx(
    space_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SpaceContext:
    actor = await get_actor(request, session)
    return await load_space_context(session, actor, space_id)

SpaceCtx = Annotated[SpaceContext, Depends(_ctx)]


def _archive_out(archive) -> dict:  # type: ignore[no-untyped-def]
    return {
        "id": str(archive.id),
        "space_id": str(archive.space_id) if archive.space_id else None,
        "kind": archive.kind.value, "status": archive.status.value,
        "expires_at": archive.expires_at.isoformat() if archive.expires_at else None,
        "last_error": archive.last_error,
        "created_at": archive.created_at.isoformat(),
    }


@router.post("/spaces/{space_id}/archives", status_code=status.HTTP_202_ACCEPTED)
async def request_export(
    body: ArchiveCreateIn,
    ctx: SpaceCtx,
    session: Annotated[AsyncSession, Depends(get_session)],
    jobs: Annotated[JobRunner, Depends(get_job_runner_dep)],
) -> dict:
    archive = await service.request_export(session, ctx, body.kind, jobs)
    return ok_payload({"archive_id": str(archive.id)})


@router.get("/spaces/{space_id}/archives")
async def list_exports(
    ctx: SpaceCtx,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    rows = await service.list_exports(session, ctx)
    out = []
    for archive in rows:
        entry = _archive_out(archive)
        if archive.status.value == "succeeded":
            entry["download_url"] = f"/v1/archives/{archive.id}/download"
        out.append(entry)
    return ok_payload(out)


@router.get("/archives/{archive_id}/download")
async def download_archive(
    archive_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    t: str | None = Query(default=None, max_length=128),
):
    actor = await get_actor(request, session)
    url = await service.download_url_for(session, actor, archive_id, t)
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)


@router.post("/archives/{archive_id}/share-link")
async def share_archive(
    archive_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    actor = await get_actor(request, session)
    url = await service.mint_share_link(session, actor, archive_id)
    return ok_payload({"url": url})


@router.get("/me/export", status_code=status.HTTP_202_ACCEPTED)
async def request_personal_export(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[UserActor, Depends(require_user)],
    jobs: Annotated[JobRunner, Depends(get_job_runner_dep)],
) -> dict:
    archive = await service.request_personal_export(session, user.user_id, jobs)
    return ok_payload({"archive_id": str(archive.id)})


@router.get("/me/archives")
async def list_personal_exports(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[UserActor, Depends(require_user)],
) -> dict:
    rows = await service.list_personal_exports(session, user.user_id)
    out = []
    for archive in rows:
        entry = _archive_out(archive)
        if archive.status.value == "succeeded":
            entry["download_url"] = f"/v1/archives/{archive.id}/download"
        out.append(entry)
    return ok_payload(out)


@router.post("/me/delete", status_code=status.HTTP_202_ACCEPTED)
async def close_account(
    body: CloseAccountIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[UserActor, Depends(require_user)],
) -> dict:
    await service.close_account(session, user.user_id, body.confirm_email)
    return ok_payload({"closed": True})


@router.post("/me/purge", status_code=status.HTTP_202_ACCEPTED)
async def purge_account(
    body: PurgeAccountIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[UserActor, Depends(require_user)],
    jobs: Annotated[JobRunner, Depends(get_job_runner_dep)],
) -> dict:
    # Re-authenticate ownership: the session must still be valid AND the
    # account already closed; purge itself runs asynchronously.
    await service.purge_account(session, user.user_id, body.confirm_email, jobs)
    return ok_payload({"purging": True})
