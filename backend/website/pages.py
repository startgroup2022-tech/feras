"""Route resolution and page metadata for the public website.

:func:`resolve_route` maps a request path to a :class:`PageMeta`. It is the one
place that decides what a public URL means, so the HTML shell, the SEO tags and
the sitemap all agree on the same set of routes.

Route shapes:

* ``/`` and ``/ar``                          -- home (English / Arabic)
* ``/<page>`` and ``/ar/<page-ar>``          -- top-level pages
* ``/<market>/<service>`` and
  ``/ar/<market-ar>/<service-ar>``           -- the indexable market/service pages
"""

from __future__ import annotations

from backend.website import content as C
from backend.website.content import PageMeta

# Brand suffix appended to every page title, per language.
_BRAND = {"ar": "ستارت أب سفير القابضة", "en": "Start Upsphere Holding"}

# Localized top-level path -> (page key, language).
_TOP_LEVEL: dict[str, tuple[str, str]] = {}
for _key, _paths in C.PAGE_PATHS.items():
    _TOP_LEVEL[_paths["en"]] = (_key, "en")
    _TOP_LEVEL[_paths["ar"]] = (_key, "ar")

# Localized market/service path -> (market, service slug, language).
_MARKET_SERVICE: dict[str, tuple[str, str, str]] = {}
for _market, _slug in C.all_market_service_pages():
    for _lang in ("en", "ar"):
        _MARKET_SERVICE[C.market_service_path(_market, _slug, _lang)] = (
            _market,
            _slug,
            _lang,
        )

# Static page titles/descriptions. Kept here (not in content.py) because they
# are page-level, whereas content.py is about the domain structure.
_PAGE_COPY: dict[str, dict[str, dict[str, str]]] = {
    "home": {
        "ar": {
            "title": "ستارت أب سفير القابضة — شركة قابضة في مملكة البحرين",
            "description": "شركة ستارت أب سفير القابضة ذ.م.م، مقرها مملكة البحرين، تمتلك محفظة من الشركات والاستثمارات في قطاعات متعددة.",
        },
        "en": {
            "title": "Start Upsphere Holding — A holding company in the Kingdom of Bahrain",
            "description": "Start Upsphere Holding Co W.L.L, based in the Kingdom of Bahrain, holds a portfolio of companies and investments across diverse sectors.",
        },
    },
    "opportunities": {
        "ar": {
            "title": "الفرص التجارية | ستارت أب سفير القابضة",
            "description": "استكشف مشاريع قائمة معروضة للبيع في دول الخليج، أو قدّم مشروعك للمراجعة والنشر.",
        },
        "en": {
            "title": "Business Opportunities | Start Upsphere Holding",
            "description": "Explore existing businesses offered for sale across the Gulf, or submit your project for review and publication.",
        },
    },
    "services": {
        "ar": {
            "title": "خدمات الأعمال | سفير القابضة",
            "description": "تأسيس الشركات، دراسات الجدوى، الشراكات والاستثمار في البحرين والسعودية.",
        },
        "en": {
            "title": "Business Services | Safir Holding",
            "description": "Company formation, feasibility studies, partnerships and investment in Bahrain and Saudi Arabia.",
        },
    },
    "group": {
        "ar": {
            "title": "شركات المجموعة | سفير القابضة",
            "description": "شركات المجموعة والكيانات المرتبطة بسفير القابضة.",
        },
        "en": {
            "title": "Group Companies | Safir Holding",
            "description": "The group companies and entities associated with Safir Holding.",
        },
    },
    "about": {
        "ar": {
            "title": "عن سفير القابضة",
            "description": "سفير القابضة طبقة تنسيق تربط المستثمرين والشركات والفرص والخدمات في البحرين والسعودية.",
        },
        "en": {
            "title": "About Safir Holding",
            "description": "Safir Holding is an orchestration layer connecting investors, companies, opportunities and services across Bahrain and Saudi Arabia.",
        },
    },
    "contact": {
        "ar": {
            "title": "تواصل معنا | سفير القابضة",
            "description": "تواصل مع سفير القابضة بشأن الفرص والخدمات في البحرين والسعودية.",
        },
        "en": {
            "title": "Contact | Safir Holding",
            "description": "Contact Safir Holding about opportunities and services in Bahrain and Saudi Arabia.",
        },
    },
    "list-your-business": {
        "ar": {
            "title": "اعرض شركتك أو مشروعك | سفير القابضة",
            "description": "قدّم شركتك أو مشروعك للبيع أو الشراكة أو الاستثمار عبر سفير القابضة.",
        },
        "en": {
            "title": "List Your Business | Safir Holding",
            "description": "Offer your business or project for sale, partnership or investment through Safir Holding.",
        },
    },
    "careers": {
        "ar": {
            "title": "الوظائف | ستارت أب سفير القابضة",
            "description": "انضم إلى فريق ستارت أب سفير القابضة وشركات المجموعة، وأرسل سيرتك الذاتية للنظر فيها عند توفر فرصة مناسبة.",
        },
        "en": {
            "title": "Careers | Start Upsphere Holding",
            "description": "Join the Start Upsphere Holding team and its group companies. Submit your CV to be considered when a suitable opportunity arises.",
        },
    },
    "terms": {
        "ar": {
            "title": "الشروط والأحكام | ستارت أب سفير القابضة",
            "description": "شروط استخدام موقع ستارت أب سفير القابضة، وطلبات الخدمات والتوظيف، وعرض المشاريع على الموقع.",
        },
        "en": {
            "title": "Terms & Conditions | Start Upsphere Holding",
            "description": "The terms of use for the Start Upsphere Holding website, covering service and career requests and the listing of businesses.",
        },
    },
    "privacy": {
        "ar": {
            "title": "سياسة الخصوصية | ستارت أب سفير القابضة",
            "description": "كيف تتعامل ستارت أب سفير القابضة مع البيانات المقدمة عبر النماذج على موقعها.",
        },
        "en": {
            "title": "Privacy Policy | Start Upsphere Holding",
            "description": "How Start Upsphere Holding handles the data submitted through the forms on its website.",
        },
    },
}


def _breadcrumb_home(lang: str) -> tuple[str, str]:
    label = "الرئيسية" if lang == "ar" else "Home"
    return (label, C.PAGE_PATHS["home"][lang])


def resolve_route(path: str) -> PageMeta | None:
    """Resolve a public path to page metadata, or ``None`` if it is not a page.

    Returns ``None`` for anything the website does not own -- the API, static
    assets, the platform -- so the caller can fall through to the next handler.
    """
    path = path.rstrip("/") or "/"

    # ---- home ----
    if path in ("/", "/ar"):
        lang = "ar" if path == "/ar" else "en"
        copy = _PAGE_COPY["home"][lang]
        return PageMeta(
            route="home",
            lang=lang,
            title=copy["title"],
            description=copy["description"],
            canonical_path=C.PAGE_PATHS["home"][lang],
            alternates={"en": C.PAGE_PATHS["home"]["en"], "ar": C.PAGE_PATHS["home"]["ar"]},
        )

    # ---- market/service ----
    if path in _MARKET_SERVICE:
        market, slug, lang = _MARKET_SERVICE[path]
        service = C.service_def(slug)
        content = C.service_market_content(slug, market)
        market_name = C.market_label(market, lang)
        service_name = service["title"][lang]
        # Prefer the dedicated per market+service copy so no two pages share a
        # title or a description (the V2 concept's "real local page" rule).
        if content is not None:
            title = f"{content['meta'][lang]['title']} | {_BRAND[lang]}"
            description = content["meta"][lang]["description"]
        else:
            title = (
                f"{service_name} في {market_name} | سفير القابضة"
                if lang == "ar"
                else f"{service_name} in {market_name} | Safir Holding"
            )
            description = C.MARKET_CONTENT[market]["meta"][lang]["description"]
        return PageMeta(
            route=f"market-service:{market}:{slug}",
            lang=lang,
            title=title,
            description=description,
            canonical_path=C.market_service_path(market, slug, lang),
            alternates={
                "en": C.market_service_path(market, slug, "en"),
                "ar": C.market_service_path(market, slug, "ar"),
            },
            breadcrumbs=[
                _breadcrumb_home(lang),
                (C.PAGE_PATHS["services"][lang], C.PAGE_PATHS["services"][lang]),
                (service_name, C.market_service_path(market, slug, lang)),
            ],
            market=market,
            service_slug=slug,
        )

    # ---- top level ----
    if path in _TOP_LEVEL:
        key, lang = _TOP_LEVEL[path]
        copy = _PAGE_COPY[key][lang]
        return PageMeta(
            route=key,
            lang=lang,
            title=copy["title"],
            description=copy["description"],
            canonical_path=C.PAGE_PATHS[key][lang],
            alternates={"en": C.PAGE_PATHS[key]["en"], "ar": C.PAGE_PATHS[key]["ar"]},
            breadcrumbs=[
                _breadcrumb_home(lang),
                (C.nav_label(key, lang), C.PAGE_PATHS[key][lang]),
            ],
        )

    return None


def not_found_meta(lang: str = "ar") -> PageMeta:
    return PageMeta(
        route="not-found",
        lang=lang,
        title="الصفحة غير موجودة | سفير القابضة" if lang == "ar" else "Page not found | Safir Holding",
        description="",
        canonical_path="/404",
        robots="noindex, follow",
    )
