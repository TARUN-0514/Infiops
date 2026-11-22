import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import (
    analytics,
    assistant,
    auth,
    automations,
    briefing,
    calendar,
    devices,
    email,
    finance,
    fitness,
    health,
    integrations,
    knowledge,
    memory,
    operator,
    personal,
    preferences,
    status,
    voice,
    work,
    workspaces,
)
from app.core.config import get_settings
from app.core.logging import configure_logging, log
from app.db.session import dispose_engine
from app.services import monitor
from app.services.jobs import close_jobs
from app.services.redis import close_redis

API_PREFIX = "/api/v1"

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Permissions-Policy": "camera=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    settings.require_secrets()
    log.info("startup", env=settings.env)
    yield
    await dispose_engine()
    await close_redis()
    await close_jobs()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="NEXUS AI API",
        version="0.1.0",
        lifespan=lifespan,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=None if settings.env == "production" else f"{API_PREFIX}/docs",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            await monitor.note_request(500, (time.perf_counter() - start) * 1000)
            raise
        finally:
            structlog.contextvars.clear_contextvars()
        response.headers["X-Request-ID"] = request_id
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if settings.cookie_secure:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        ms = round((time.perf_counter() - start) * 1000, 1)
        # Streaming replies (chat) return here at the first byte, so this is time to answer.
        slow = ms >= settings.slow_request_ms
        (log.warning if slow or response.status_code >= 500 else log.info)(
            "slow_request" if slow else "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            ms=ms,
            request_id=request_id,
        )
        if request.url.path.startswith(API_PREFIX):
            await monitor.note_request(response.status_code, ms)
        return response

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        detail = (
            exc.detail
            if isinstance(exc.detail, dict)
            else {"code": "error", "message": str(exc.detail)}
        )
        return JSONResponse({"error": detail}, status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]}
            for e in exc.errors()
        ]
        return JSONResponse(
            {
                "error": {
                    "code": "validation_error",
                    "message": "Check the highlighted fields.",
                    "fields": fields,
                }
            },
            status_code=422,
        )

    app.include_router(health.router)
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(assistant.router, prefix=API_PREFIX)
    app.include_router(memory.router, prefix=API_PREFIX)
    app.include_router(work.router, prefix=API_PREFIX)
    for module in (
        operator,  # before integrations: /integrations/github must win over /{account_id}
        integrations,
        email,
        calendar,
        knowledge,
        briefing,
        voice,
        devices,
        preferences,
        finance,
        fitness,
        workspaces,
        personal,
        automations,
        analytics,
        status,
    ):
        app.include_router(module.router, prefix=API_PREFIX)
    return app


app = create_app()
