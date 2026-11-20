"""FastAPI application factory."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app import db
from app.config import get_settings, reset_settings_cache
from app.deps import close_redis_client
from app.errors import install_error_handlers
from app.health import router as health_router
from app.logging import configure_logging, get_logger, request_id_ctx
from app.modules.archives.routes import router as archives_router
from app.modules.contributions.routes import router as contributions_router
from app.modules.identity.routes import router as identity_router
from app.modules.media.routes import router as media_router
from app.modules.scheduling.routes import router as scheduling_router
from app.modules.spaces.routes import router as spaces_router
from app.modules.studio.routes import router as studio_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    db.init_engine(settings)
    logger.info("startup", extra={})  # structured fields come from the formatter
    yield
    await close_redis_client()
    await db.dispose_engine()
    reset_settings_cache()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)

    app = FastAPI(
        title="Memory Lane API",
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
        openapi_url="/v1/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "PUT"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    )

    # NOTE: Starlette runs middleware in reverse registration order, so the
    # CSRF check is registered first (runs inner) and request-id last (outer).
    @app.middleware("http")
    async def csrf_origin_middleware(request: Request, call_next) -> Response:
        # Browser CSRF backstop for cookie-authenticated mutations: the session
        # cookie is SameSite=Lax, and state-changing requests must carry an
        # Origin/Referer from our allow-list (or be same-origin fetches).
        # Errors render here (not via handlers: middleware sits outside them).
        from fastapi.responses import JSONResponse

        from app.errors import AppError, error_payload

        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and settings.session_cookie_name in (
            request.cookies or {}
        ):
            origin = request.headers.get("origin") or request.headers.get("referer", "")
            allowed = [o.rstrip("/") for o in settings.allowed_origins]
            if origin and not any(origin.rstrip("/").startswith(a) for a in allowed):
                denied = AppError("forbidden", "Cross-origin request refused.", 403)
                return JSONResponse(status_code=403, content=error_payload(denied))
        return await call_next(request)

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
        request.state.request_id = request_id
        token = request_id_ctx.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        response.headers["X-Request-Id"] = request_id
        return response

    install_error_handlers(app)
    app.include_router(health_router)
    app.include_router(identity_router, prefix="/v1")
    app.include_router(spaces_router, prefix="/v1")
    app.include_router(archives_router, prefix="/v1")
    app.include_router(contributions_router, prefix="/v1")
    app.include_router(media_router, prefix="/v1")
    app.include_router(studio_router, prefix="/v1")
    app.include_router(scheduling_router, prefix="/v1")
    return app


app = create_app()
