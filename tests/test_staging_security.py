"""Staging security configuration: secrets, docs exposure, CORS and rate limits.

These lock in the staging hardening requirements without needing a live staging
host: the production secret guard, DEBUG defaults, Swagger exposure rules, CORS
parsing, and the in-process login rate limiter.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.core.config import Settings
from backend.core.rate_limit import RateLimiter


# --------------------------------------------------------------------------
# secret handling
# --------------------------------------------------------------------------
def test_production_rejects_the_dev_default_secret():
    with pytest.raises(ValidationError, match="SECRET_KEY must be set"):
        Settings(APP_ENV="production", SECRET_KEY="dev-only-insecure-change-me")


def test_production_accepts_a_strong_secret():
    settings = Settings(APP_ENV="production", SECRET_KEY="a" * 64)
    assert settings.is_production is True


def test_development_may_use_the_insecure_default():
    settings = Settings(APP_ENV="development", SECRET_KEY="dev-only-insecure-change-me")
    assert settings.is_production is False


def test_production_rejects_a_short_secret():
    """A 5-character secret is not a secret; length is the enforceable floor."""
    with pytest.raises(ValidationError, match="at least 32"):
        Settings(APP_ENV="production", SECRET_KEY="abc12")


def test_production_rejects_a_reused_fixture_secret():
    with pytest.raises(ValidationError, match="SECRET_KEY must be set"):
        Settings(APP_ENV="production",
                 SECRET_KEY="test-secret-key-not-used-in-production")


def test_production_rejects_common_placeholder_words():
    for weak in ("changeme", "secret", "password"):
        with pytest.raises(ValidationError):
            Settings(APP_ENV="production", SECRET_KEY=weak)


# --------------------------------------------------------------------------
# debug + docs defaults
# --------------------------------------------------------------------------
def test_debug_defaults_to_false():
    assert Settings().DEBUG is False


def test_docs_enabled_by_default_for_non_production():
    settings = Settings(APP_ENV="staging", DOCS_ENABLED=True)
    assert settings.DOCS_ENABLED is True
    assert (settings.DOCS_ENABLED and not settings.is_production) is True


def test_docs_are_never_exposed_in_production():
    """Even if DOCS_ENABLED is left true, production must hide OpenAPI."""
    settings = Settings(APP_ENV="production", SECRET_KEY="a" * 64, DOCS_ENABLED=True)
    assert (settings.DOCS_ENABLED and not settings.is_production) is False


def test_docs_can_be_switched_off_for_staging():
    settings = Settings(APP_ENV="staging", DOCS_ENABLED=False)
    assert (settings.DOCS_ENABLED and not settings.is_production) is False


def test_create_app_hides_docs_in_production(monkeypatch):
    import backend.main as main_module

    monkeypatch.setattr(main_module.settings, "APP_ENV", "production", raising=False)
    monkeypatch.setattr(main_module.settings, "SECRET_KEY", "a" * 64, raising=False)

    app = main_module.create_app()

    assert app.docs_url is None
    assert app.openapi_url is None


# --------------------------------------------------------------------------
# CORS
# --------------------------------------------------------------------------
def test_cors_origins_are_split_and_trimmed():
    settings = Settings(CORS_ORIGINS="https://a.example, https://b.example ")
    assert settings.cors_origin_list == ["https://a.example", "https://b.example"]


def test_staging_cors_accepts_an_https_origin():
    settings = Settings(CORS_ORIGINS="https://staging.safir.example")
    assert settings.cors_origin_list == ["https://staging.safir.example"]


# --------------------------------------------------------------------------
# rate limiter (in-process)
# --------------------------------------------------------------------------
def test_rate_limiter_allows_up_to_the_limit():
    limiter = RateLimiter(max_events=3, window_seconds=300)
    assert [limiter.check("ip") for _ in range(3)] == [True, True, True]


def test_rate_limiter_blocks_past_the_limit():
    limiter = RateLimiter(max_events=3, window_seconds=300)
    for _ in range(3):
        limiter.check("ip")
    assert limiter.check("ip") is False


def test_rate_limiter_is_per_key():
    limiter = RateLimiter(max_events=1, window_seconds=300)
    assert limiter.check("a") is True
    assert limiter.check("a") is False
    assert limiter.check("b") is True


def test_rate_limiter_retry_after_is_positive_when_limited():
    limiter = RateLimiter(max_events=1, window_seconds=300)
    limiter.check("ip")
    assert limiter.retry_after("ip") >= 1


def test_rate_limiter_reset_clears_state():
    limiter = RateLimiter(max_events=1, window_seconds=300)
    limiter.check("ip")
    limiter.reset("ip")
    assert limiter.check("ip") is True


def test_rate_limiter_window_expiry(monkeypatch):
    """Once the window passes, the counter clears."""
    import backend.core.rate_limit as rl

    clock = {"now": 1000.0}
    monkeypatch.setattr(rl.time, "monotonic", lambda: clock["now"])

    limiter = RateLimiter(max_events=1, window_seconds=10)
    assert limiter.check("ip") is True
    assert limiter.check("ip") is False
    clock["now"] += 11
    assert limiter.check("ip") is True


# --------------------------------------------------------------------------
# upload limits (unit level)
# --------------------------------------------------------------------------
def test_upload_limit_is_ten_mib():
    from backend.core import storage

    assert storage.MAX_ATTACHMENT_BYTES == 10 * 1024 * 1024


@pytest.mark.parametrize(
    ("content_type", "expected_ext"),
    [
        ("application/pdf", ".pdf"),
        ("image/png", ".png"),
        ("image/jpeg", ".jpg"),
        ("text/csv", ".csv"),
    ],
)
def test_allowed_content_types_map_to_extensions(content_type, expected_ext):
    from backend.core import storage

    assert storage.ALLOWED_CONTENT_TYPES[content_type] == expected_ext


def test_oversized_upload_is_rejected():
    from backend.core import storage
    from backend.core.errors import ValidationError

    with pytest.raises(ValidationError, match="10 MB"):
        storage.validate_upload(
            filename="big.pdf",
            content_type="application/pdf",
            size=storage.MAX_ATTACHMENT_BYTES + 1,
        )


def test_empty_upload_is_rejected():
    from backend.core import storage
    from backend.core.errors import ValidationError

    with pytest.raises(ValidationError, match="empty"):
        storage.validate_upload(filename="x.pdf", content_type="application/pdf", size=0)


def test_disallowed_type_is_rejected():
    from backend.core import storage
    from backend.core.errors import ValidationError

    with pytest.raises(ValidationError, match="not permitted"):
        storage.validate_upload(
            filename="x.exe", content_type="application/x-msdownload", size=10
        )


# --------------------------------------------------------------------------
# reverse-proxy profile
# --------------------------------------------------------------------------
NGINX_DIR = Path(__file__).resolve().parents[1] / "deploy" / "nginx"
SITE = NGINX_DIR / "safir-staging.conf"
HEADERS = NGINX_DIR / "safir-security-headers.conf"

SECURITY_HEADERS = (
    "Strict-Transport-Security",
    "Content-Security-Policy",
    "X-Content-Type-Options",
    "X-Frame-Options",
    "Referrer-Policy",
)


def test_security_header_snippet_defines_every_header():
    text = HEADERS.read_text()
    for header in SECURITY_HEADERS:
        assert header in text, header


def test_every_add_header_location_reincludes_the_security_headers():
    """nginx replaces, never merges, ``add_header`` across levels.

    A ``location`` that declares its own ``add_header`` (e.g. a Cache-Control
    for static assets) therefore *drops* the server-level security headers for
    its responses unless it re-includes them. This guards against that silent
    regression, which is invisible in a browser and only shows up in a header
    scan of those specific URLs.
    """
    site = SITE.read_text()
    blocks = re.findall(r"location[^{]*\{[^}]*\}", site)
    assert blocks, "no location blocks found"
    for block in blocks:
        if "add_header" in block:
            assert "safir-security-headers.conf" in block, (
                "a location with add_header must re-include the security "
                f"headers: {block.splitlines()[0].strip()}"
            )


def test_nginx_profile_compresses_and_caches_the_platform_assets():
    site = SITE.read_text()
    assert "gzip on;" in site
    # app.js has no content hash, so a long immutable cache would pin a stale
    # shell across deploys.
    assert "immutable" not in site.split("location ~ ^/platform/")[1]
    assert "expires 5m;" in site
