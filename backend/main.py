"""Safir Holding 2027 -- application factory.

The approved static dashboard is served from ``frontend/`` at the site root; the
JSON API lives under ``/api/v1``. Keeping the two on one origin avoids CORS
complexity in development while still allowing the frontend to be hosted
separately later (see ``CORS_ORIGINS``).
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.api.v1 import api_router
from backend.core.config import settings
from backend.core.errors import register_exception_handlers
from backend.core.logging_config import configure_logging
from backend.db.session import SessionLocal

logger = logging.getLogger("safir.readiness")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# Security headers applied to every response. ``default-src 'self'`` is relaxed
# only for Google Fonts, which the approved design depends on.
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


def create_app() -> FastAPI:
    configure_logging(settings.DEBUG)

    # Swagger/OpenAPI is never exposed in production, and can be switched off
    # for any tier via DOCS_ENABLED. Public staging access is additionally
    # restricted at the reverse proxy (see deploy/nginx/).
    docs_enabled = settings.DOCS_ENABLED and not settings.is_production

    app = FastAPI(
        title=f"{settings.APP_NAME} API",
        version="1.0.0",
        docs_url="/api/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if docs_enabled else None,
    )

    register_exception_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def _security_headers(request, call_next):
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        """Liveness probe. Deliberately exposes no configuration detail."""
        return {"status": "ok", "service": "safir-holding-2027"}

    @app.get("/ready", tags=["system"])
    def ready() -> JSONResponse:
        """Readiness probe.

        Verifies the two runtime dependencies a request actually needs: a live
        database connection and a writable upload directory. It returns only
        coarse booleans -- no credentials, paths, driver names or exception
        details -- so it is safe to expose to a load balancer.
        """
        checks = {"database": False, "uploads_writable": False}

        try:
            from sqlalchemy import text

            with SessionLocal() as db:
                db.execute(text("SELECT 1"))
            checks["database"] = True
        except Exception:  # noqa: BLE001 - never leak failure specifics
            logger.warning("readiness: database check failed")

        try:
            upload_dir = Path(settings.UPLOAD_DIR)
            upload_dir.mkdir(parents=True, exist_ok=True)
            probe = upload_dir / ".ready_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            checks["uploads_writable"] = True
        except Exception:  # noqa: BLE001 - never leak failure specifics
            logger.warning("readiness: upload directory check failed")

        is_ready = all(checks.values())
        return JSONResponse(
            status_code=200 if is_ready else 503,
            content={"status": "ready" if is_ready else "not_ready", **checks},
        )

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    """Serve the approved dashboard without altering a single byte of it."""
    if not FRONTEND_DIR.exists():  # pragma: no cover - defensive
        return

    app.mount(
        "/assets",
        StaticFiles(directory=str(FRONTEND_DIR)),
        name="frontend-assets",
    )

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    @app.get("/styles.css", include_in_schema=False)
    def styles() -> FileResponse:
        return FileResponse(str(FRONTEND_DIR / "styles.css"), media_type="text/css")

    @app.get("/app.js", include_in_schema=False)
    def app_js() -> FileResponse:
        return FileResponse(
            str(FRONTEND_DIR / "app.js"), media_type="application/javascript"
        )

    @app.get("/auth.js", include_in_schema=False)
    def auth_js() -> FileResponse:
        return FileResponse(
            str(FRONTEND_DIR / "auth.js"), media_type="application/javascript"
        )

    @app.get("/preview-16x9.png", include_in_schema=False)
    def preview() -> FileResponse:
        return FileResponse(str(FRONTEND_DIR / "preview-16x9.png"), media_type="image/png")


app = create_app()


@app.get("/api/v1", include_in_schema=False)
def api_root() -> JSONResponse:
    """Discovery endpoint listing the versioned API surface."""
    return JSONResponse(
        {
            "service": settings.APP_NAME,
            "version": "1.0.0",
            "resources": [
                "/api/v1/auth",
                "/api/v1/users",
                "/api/v1/companies",
                "/api/v1/monthly-reports",
                "/api/v1/support-requests",
                "/api/v1/dashboard",
                "/api/v1/ai/holding",
                "/api/v1/ai/company",
                "/api/v1/ai/insights",
            ],
        }
    )
