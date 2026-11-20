"""Liveness and readiness probes (SYSTEM_ARCHITECTURE Section 11)."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app import db
from app.config import get_settings
from app.deps import get_redis_client

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def liveness() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "version": settings.app_version}


@router.get("/readyz")
async def readiness() -> dict[str, object]:
    settings = get_settings()
    components: dict[str, str] = {}
    try:
        async with db.session_scope() as session:
            await session.execute(text("SELECT 1"))
        components["database"] = "ok"
    except Exception:
        components["database"] = "error"
    if settings.uses_redis:
        try:
            client = get_redis_client()
            await client.ping()
            components["redis"] = "ok"
        except Exception:
            components["redis"] = "error"
    else:
        components["redis"] = "disabled"
    ready = all(v in {"ok", "disabled"} for v in components.values())
    return {"ready": ready, "version": settings.app_version, "components": components}
