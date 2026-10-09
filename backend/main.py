"""Safir Holding 2027 -- application factory.

Two distinct experiences share one origin:

* the **public website** (``website/``), served at the site root and built for
  search engines, and
* the **internal platform** (``frontend/``), the authenticated operational
  application, served under ``PLATFORM_PATH`` and marked ``noindex``.

Keeping both on one origin avoids CORS complexity while still allowing either
to be hosted separately later (see ``CORS_ORIGINS``). The JSON API lives under
``/api/v1``.

The website is rendered server-side so each market/service route is a real,
crawlable document; the platform remains the unchanged static application it
always was, just relocated so the public site can own the root.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.api.v1 import api_router
from backend.core.config import settings
from backend.core.errors import register_exception_handlers
from backend.core.logging_config import configure_logging
from backend.db.session import SessionLocal
from backend.services import branding_service
from backend.website import pages as website_pages
from backend.website import renderer as website_renderer
from backend.website import seo as website_seo
from backend.website import cms_context as website_cms_context

logger = logging.getLogger("safir.readiness")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"

# Security headers applied to every response. ``default-src 'self'`` is relaxed
# only for Google Fonts, which both experiences depend on.
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}

# The platform and the API are never indexable. The header is belt-and-braces
# with robots.txt: it also covers responses robots.txt cannot reach.
NOINDEX_PREFIXES = ("/api/",)


def _platform_prefix() -> str:
    return settings.PLATFORM_PATH.rstrip("/") or "/platform"


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
        path = request.url.path
        if path.startswith(NOINDEX_PREFIXES) or path.startswith(_platform_prefix()):
            response.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
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
                    "/api/v1/public",
                    "/api/v1/leads",
                ],
            }
        )

    # Order matters: the platform and the website's catch-all are registered so
    # that more specific routes always win. The catch-all is inside
    # ``_mount_website`` and therefore registered last.
    _mount_seo(app)
    _mount_platform(app)
    _mount_website(app)
    return app


# --------------------------------------------------------------------------
# public website (SEO files, server-rendered pages)
# --------------------------------------------------------------------------
def _mount_seo(app: FastAPI) -> None:
    @app.get("/robots.txt", include_in_schema=False)
    def robots() -> PlainTextResponse:
        return PlainTextResponse(website_seo.robots_txt(), media_type="text/plain")

    @app.get("/sitemap.xml", include_in_schema=False)
    def sitemap() -> Response:
        return Response(website_seo.sitemap_xml(), media_type="application/xml")


def _public_branding() -> dict | None:
    """Branding for the website shell, or ``None`` to use the built-in mark.

    The public site must render even if the database is momentarily
    unavailable, so any failure degrades to the fallback logo rather than a
    500 on a marketing page.
    """
    db = SessionLocal()
    try:
        return branding_service.branding_payload(db)
    except Exception:  # noqa: BLE001 - never break a public page over branding
        logger.warning("Branding lookup failed; using the fallback mark.", exc_info=True)
        return None
    finally:
        db.close()


def _public_cms():
    """Published CMS context for the public shell, or ``None`` on any failure.

    Best-effort by design: an empty or unreachable CMS degrades to the built-in
    V2 content instead of breaking a marketing page.
    """
    db = SessionLocal()
    try:
        return website_cms_context.load(db)
    except Exception:  # noqa: BLE001 - never break a public page over the CMS
        logger.warning("Website CMS lookup failed; using built-in content.", exc_info=True)
        return None
    finally:
        db.close()


def _maintenance_state() -> tuple[bool, str | None, str | None]:
    """Read the CMS maintenance flag, degrading to "off" on any failure."""
    db = SessionLocal()
    try:
        return website_cms_context.maintenance(db)
    except Exception:  # noqa: BLE001
        logger.warning("Maintenance lookup failed; serving the site.", exc_info=True)
        return False, None, None


def _render_or_404(path: str) -> Response:
    meta = website_pages.resolve_route(path)
    if meta is None:
        meta = website_pages.not_found_meta("ar")
        return Response(
            website_renderer.render(meta, _public_branding(), _public_cms()),
            status_code=404,
            media_type="text/html",
        )
    return Response(
        website_renderer.render(meta, _public_branding(), _public_cms()),
        media_type="text/html",
    )


def _mount_website(app: FastAPI) -> None:
    """Serve the public website.

    Static assets are mounted from ``website/``; the ``catch-all`` page route is
    registered last so it never shadows the API or the platform. When the site
    is not split from the platform (development default), the website still owns
    only its own paths and the platform keeps the root -- so local workflows are
    unchanged.
    """
    assets_dir = WEBSITE_DIR / "assets"
    if assets_dir.exists():
        app.mount(
            "/website/assets",
            StaticFiles(directory=str(assets_dir)),
            name="website-assets",
        )

    @app.get("/website/{rest:path}", include_in_schema=False)
    def website_extra(rest: str) -> Response:
        # Unknown /website/* asset -> 404 rather than the HTML shell.
        return Response(status_code=404)

    @app.get("/{full_path:path}", include_in_schema=False)
    def website_page(full_path: str) -> Response:
        path = "/" + full_path if full_path else "/"
        # Never intercept the API or the platform; those are handled above.
        if path.startswith("/api/") or path.startswith(_platform_prefix()):
            return Response(status_code=404)
        if not settings.SPLIT_PUBLIC_SITE:
            # Development: the platform still owns the root and its assets.
            if path == "/" or path in _PLATFORM_ASSETS or path.startswith("/assets/"):
                return _serve_platform_asset(path)
        maintenance_on, message_ar, message_en = _maintenance_state()
        if maintenance_on:
            lang = "en" if (path == "/en" or path.startswith("/en/")) else "ar"
            message = message_en if lang == "en" else message_ar
            return Response(
                website_renderer.maintenance_page(lang, message),
                status_code=503,
                media_type="text/html",
                headers={"Retry-After": "3600"},
            )
        return _render_or_404(path)


# --------------------------------------------------------------------------
# internal platform (unchanged static application, relocated)
# --------------------------------------------------------------------------
_PLATFORM_ASSETS = {
    "/styles.css",
    "/app.js",
    "/auth.js",
    "/preview-16x9.png",
}


def _serve_platform_asset(path: str) -> Response:
    """Serve a platform file, mapping the asset root for both layouts.

    The platform's ``index.html`` references ``styles.css``/``app.js`` relative
    to the page, so under ``/platform/`` those resolve to ``/platform/...``.
    This handler serves them from either the root or the prefixed path, so the
    same files work whether or not the site is split.
    """
    if not FRONTEND_DIR.exists():  # pragma: no cover - defensive
        return Response(status_code=404)

    if path == "/":
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    if path.startswith("/assets/"):
        candidate = FRONTEND_DIR / path[len("/assets/"):]
    else:
        candidate = FRONTEND_DIR / path.lstrip("/")

    if not candidate.is_file():
        return Response(status_code=404)

    media = {
        ".css": "text/css",
        ".js": "application/javascript",
        ".png": "image/png",
        ".svg": "image/svg+xml",
    }.get(candidate.suffix, "application/octet-stream")
    return FileResponse(str(candidate), media_type=media)


def _mount_platform(app: FastAPI) -> None:
    if not FRONTEND_DIR.exists():  # pragma: no cover - defensive
        return

    prefix = _platform_prefix()

    @app.get(prefix, include_in_schema=False)
    def platform_index_redirect() -> Response:
        # A bare ``/platform`` has no trailing slash, so the shell's relative
        # asset references (``styles.css``, ``auth.js``) would resolve against
        # the root and 404. Redirect to the canonical slashed URL instead.
        return RedirectResponse(url=prefix + "/", status_code=307)

    @app.get(prefix + "/", include_in_schema=False)
    def platform_index() -> Response:
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    @app.get(prefix + "/{rest:path}", include_in_schema=False)
    def platform_asset(rest: str) -> Response:
        """Serve a platform file, falling back to the shell for deep links.

        The platform references its assets relatively (``styles.css``,
        ``app.js``), so under ``/platform/`` those resolve to
        ``/platform/styles.css`` and friends. An existing file is served as-is;
        anything else is a hash route inside the app, so the shell is returned
        and the app's own router takes over.
        """
        candidate = (FRONTEND_DIR / rest).resolve()
        # Guard against traversal: only serve files inside the frontend dir.
        if FRONTEND_DIR.resolve() in candidate.parents and candidate.is_file():
            return _serve_platform_asset("/" + rest)
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    # In development (site not split) the platform keeps the root too.
    if not settings.SPLIT_PUBLIC_SITE:
        app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend-assets")


app = create_app()
