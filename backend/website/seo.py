"""Technical SEO for the public website.

Everything indexable is generated from :mod:`backend.website.content`, so the
sitemap, the canonical tags, the hreflang alternates and the structured data
all describe exactly the same set of pages. A page that is not in the content
model cannot end up in the sitemap by accident.

Structured data is limited to what is factually supported: an
``Organization`` for the Holding (name only -- no invented address, phone,
founding date or award) and ``BreadcrumbList`` for navigation. No
``aggregateRating``, no ``Review``, no ``Offer`` with a fabricated price.
"""

from __future__ import annotations

import html
import json

from backend.core.config import settings
from backend.website import content as C


def base_url() -> str:
    """Absolute site origin, without a trailing slash. May be empty in dev."""
    return settings.WEBSITE_BASE_URL.rstrip("/")


def absolute(path: str) -> str:
    base = base_url()
    if not base:
        return path
    return f"{base}{path}"


def _esc(value: str) -> str:
    return html.escape(value, quote=True)


# --------------------------------------------------------------------------
# per-page metadata
# --------------------------------------------------------------------------
def render_meta_tags(meta: C.PageMeta) -> str:
    """The ``<head>`` block for a page: title, description, canonical, social.

    Returns raw HTML ready to drop into the shell. All interpolated values are
    escaped, and JSON-LD is serialised with ``json.dumps`` so a quote in a
    title cannot break out of the script element.
    """
    canonical = absolute(meta.canonical_path)
    parts = [
        f'<title>{_esc(meta.title)}</title>',
        f'<meta name="description" content="{_esc(meta.description)}">',
        f'<meta name="robots" content="{_esc(meta.robots)}">',
        f'<link rel="canonical" href="{_esc(canonical)}">',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
    ]

    # hreflang: one alternate per language plus x-default pointing at English.
    for lang, path in meta.alternates.items():
        parts.append(
            f'<link rel="alternate" hreflang="{_esc(lang)}" href="{_esc(absolute(path))}">'
        )
    if meta.alternates.get("en"):
        parts.append(
            f'<link rel="alternate" hreflang="x-default" '
            f'href="{_esc(absolute(meta.alternates["en"]))}">'
        )

    # Open Graph / Twitter.
    parts += [
        f'<meta property="og:type" content="{_esc(meta.og_type)}">',
        f'<meta property="og:title" content="{_esc(meta.title)}">',
        f'<meta property="og:description" content="{_esc(meta.description)}">',
        f'<meta property="og:url" content="{_esc(canonical)}">',
        f'<meta property="og:locale" content="{"ar_SA" if meta.lang == "ar" else "en_US"}">',
        f'<meta property="og:site_name" content="{"سفير القابضة" if meta.lang == "ar" else "Safir Holding"}">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{_esc(meta.title)}">',
        f'<meta name="twitter:description" content="{_esc(meta.description)}">',
    ]
    return "\n".join(parts)


def organization_jsonld(lang: str) -> dict:
    """Minimal, factually-supported Organization node.

    Only the name and the site URL are asserted. Address, telephone, founding
    date, logo and social profiles are deliberately omitted because they are
    not verified project data.
    """
    name = "سفير القابضة" if lang == "ar" else "Safir Holding"
    alt = "Safir Holding" if lang == "ar" else "سفير القابضة"
    node = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": name,
        "alternateName": alt,
        "url": absolute("/"),
    }
    return node


def breadcrumb_jsonld(crumbs: list[tuple[str, str]]) -> dict | None:
    if not crumbs:
        return None
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": index + 1,
                "name": name,
                "item": absolute(path),
            }
            for index, (name, path) in enumerate(crumbs)
        ],
    }


def jsonld_script(data: dict) -> str:
    # ``</`` is escaped so the payload can never terminate the script element.
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return f'<script type="application/ld+json">{payload}</script>'


# --------------------------------------------------------------------------
# site-wide files
# --------------------------------------------------------------------------
def robots_txt() -> str:
    """robots.txt.

    The public site is fully crawlable; the internal platform and the API are
    disallowed so an authenticated application is never indexed. The sitemap is
    advertised only when an absolute origin is configured.
    """
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /api/",
        f"Disallow: {settings.PLATFORM_PATH}",
        "Disallow: /assets/",
    ]
    if base_url():
        lines.append(f"Sitemap: {absolute('/sitemap.xml')}")
    return "\n".join(lines) + "\n"


def sitemap_xml() -> str:
    """Sitemap covering every public page in both languages.

    Each URL carries its two hreflang alternates inline, which is what search
    engines expect for a bilingual site.
    """
    urls: list[str] = []

    def _add(path_en: str, path_ar: str) -> None:
        for path, lang in ((path_en, "en"), (path_ar, "ar")):
            urls.append(
                "  <url>\n"
                f"    <loc>{_esc(absolute(path))}</loc>\n"
                f'    <xhtml:link rel="alternate" hreflang="en" href="{_esc(absolute(path_en))}"/>\n'
                f'    <xhtml:link rel="alternate" hreflang="ar" href="{_esc(absolute(path_ar))}"/>\n'
                f'    <xhtml:link rel="alternate" hreflang="x-default" href="{_esc(absolute(path_en))}"/>\n'
                "  </url>"
            )

    for key, paths in C.PAGE_PATHS.items():
        _add(paths["en"], paths["ar"])

    for market, slug in C.all_market_service_pages():
        _add(
            C.market_service_path(market, slug, "en"),
            C.market_service_path(market, slug, "ar"),
        )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
        '        xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    )
