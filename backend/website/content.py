"""Public website content model.

The site is organised around *what the visitor needs*, then the market -- not
around the Holding's subsidiaries. This module is the single source of truth
for that structure: services, markets, navigation and the copy that describes
each market/service page.

Why a Python model instead of a CMS: the content is small, changes rarely and
benefits from being reviewed in code. It also lets the same definitions drive
the HTML pages, the ``sitemap.xml``, the canonical/hreflang alternates and the
breadcrumb structured data, so those can never drift apart.

Content rules (see the project brief): never invent statistics, transaction
values, client counts, approvals, awards, partnerships, years or locations.
Where a fact is not verified it is simply absent and the copy stays
conservative.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# The two markets, in the order they should appear in the UI.
MARKETS: tuple[str, ...] = ("bahrain", "saudi")

# Short, URL-safe Arabic market slugs. Kept explicit rather than derived from
# the display label so a copy tweak never silently changes a public URL.
MARKET_SLUG_AR: dict[str, str] = {"bahrain": "البحرين", "saudi": "السعودية"}

MARKET_LABELS: dict[str, dict[str, str]] = {
    "bahrain": {"ar": "البحرين", "en": "Bahrain"},
    "saudi": {"ar": "المملكة العربية السعودية", "en": "Saudi Arabia"},
}

# The services that have a dedicated, indexable page per market. ``slug`` is the
# English URL segment; ``slug_ar`` is the Arabic one. Keeping both means the
# Arabic site has genuinely Arabic URLs rather than transliterations.
SERVICES: dict[str, dict] = {
    "company-formation": {
        "key": "company_formation",
        "slug": "company-formation",
        "slug_ar": "تأسيس-شركة",
        "icon": "formation",
        "title": {"ar": "تأسيس شركة", "en": "Company Formation"},
        "blurb": {
            "ar": "ابدأ إجراءات تأسيس شركتك حسب السوق المختار.",
            "en": "Start your company formation in the market you choose.",
        },
        "form": "company-formation",
    },
    "feasibility-study": {
        "key": "feasibility_study",
        "slug": "feasibility-study",
        "slug_ar": "دراسة-جدوى",
        "icon": "feasibility",
        "title": {"ar": "دراسة جدوى", "en": "Feasibility Study"},
        "blurb": {
            "ar": "اطلب دراسة للسوق البحريني أو السعودي قبل الاستثمار.",
            "en": "Commission a market study for Bahrain or Saudi Arabia.",
        },
        "form": "feasibility",
    },
    "opportunities": {
        "key": "opportunities",
        "slug": "opportunities",
        "slug_ar": "الفرص-والمشاريع",
        "icon": "opportunities",
        "title": {"ar": "مشاريع وفرص للبيع", "en": "Projects & Opportunities"},
        "blurb": {
            "ar": "استعرض فرصًا متاحة في البحرين أو السعودية.",
            "en": "Browse available opportunities in Bahrain or Saudi Arabia.",
        },
        "form": None,
    },
    "investment": {
        "key": "investment",
        "slug": "investment",
        "slug_ar": "الاستثمار",
        "icon": "investment",
        "title": {"ar": "فرص استثمار", "en": "Investment Opportunities"},
        "blurb": {
            "ar": "فرص استثمارية وشراكات في السوقين.",
            "en": "Investment and partnership opportunities in both markets.",
        },
        "form": "opportunity-interest",
    },
}

# Market-specific page copy. Each market/service page has its own content, CTA
# and SEO metadata -- deliberately not the same text with the country swapped.
MARKET_CONTENT: dict[str, dict] = {
    "bahrain": {
        "meta": {
            "ar": {
                "title": "البحرين",
                "description": "خدمات الأعمال والاستثمار في مملكة البحرين عبر سفير القابضة.",
            },
            "en": {
                "title": "Bahrain",
                "description": "Business and investment services in the Kingdom of Bahrain with Safir Holding.",
            },
        },
        "intro": {
            "ar": "مملكة البحرين سوق مفتوح للأعمال، وقاعدة مناسبة للانطلاق نحو المنطقة.",
            "en": "The Kingdom of Bahrain is an open business market and a practical base for the region.",
        },
        "highlights": {
            "ar": [
                "بيئة أعمال مرنة ومنفتحة على المستثمر الأجنبي",
                "قرب جغرافي من السوق السعودي",
                "قطاعات خدماتية وتجارية وصناعية متنوعة",
            ],
            "en": [
                "A flexible business environment open to foreign investors",
                "Geographic proximity to the Saudi market",
                "A broad mix of services, trading and industrial sectors",
            ],
        },
    },
    "saudi": {
        "meta": {
            "ar": {
                "title": "المملكة العربية السعودية",
                "description": "خدمات الأعمال والاستثمار في المملكة العربية السعودية عبر سفير القابضة.",
            },
            "en": {
                "title": "Saudi Arabia",
                "description": "Business and investment services in Saudi Arabia with Safir Holding.",
            },
        },
        "intro": {
            "ar": "السوق السعودي هو الأكبر في المنطقة، ويستقطب المشاريع والمستثمرين.",
            "en": "The Saudi market is the region's largest and continues to attract projects and investors.",
        },
        "highlights": {
            "ar": [
                "سوق واسع ونمو مستمر في القطاعات غير النفطية",
                "مسارات متعددة للترخيص والاستثمار حسب النشاط",
                "مدن رئيسية ذات أولويات اقتصادية واضحة",
            ],
            "en": [
                "A large market with sustained growth in non-oil sectors",
                "Multiple licensing and investment paths by activity",
                "Major cities with clear economic priorities",
            ],
        },
    },
}

# Group companies shown for trust and credibility only. They are never the
# primary service navigation. Nothing here is invented: an entity is only added
# when verified, so the list is intentionally short and each entry is marked
# with its verification state for the internal review that will confirm it.
GROUP_COMPANIES: list[dict] = [
    {
        "code": "alam-damac",
        "name_ar": "مركز عالم داماك للأعمال",
        "name_en": "Alam Damac Business Centre",
        "country": "bahrain",
        "sector": {"ar": "خدمات أعمال", "en": "Business Services"},
        "description": {
            "ar": "مركز أعمال يقدم خدمات مؤسسية ودعمًا للشركات.",
            "en": "A business centre providing corporate services and company support.",
        },
        "verified": False,
    },
    {
        "code": "rukn-alriyada",
        "name_ar": "ركن الريادة",
        "name_en": "Rukn Al Riyada",
        "country": "bahrain",
        "sector": {"ar": "قانون", "en": "Legal"},
        "description": {
            "ar": "خدمات قانونية واستشارات للشركات والأفراد.",
            "en": "Legal services and consultancy for companies and individuals.",
        },
        "verified": False,
    },
    {
        "code": "damac-world",
        "name_ar": "داماك ورلد التجارية",
        "name_en": "Damac World Trading",
        "country": "bahrain",
        "sector": {"ar": "تجارة", "en": "Trading"},
        "description": {
            "ar": "أنشطة تجارية وتوريد ضمن المجموعة.",
            "en": "Trading and supply activities within the group.",
        },
        "verified": False,
    },
]

# Navigation. ``path`` is the canonical English route; ``path_ar`` is its
# Arabic mirror.
NAV: list[dict] = [
    {"key": "home", "path": "/", "path_ar": "/ar", "label": {"ar": "الرئيسية", "en": "Home"}},
    {
        "key": "opportunities",
        "path": "/opportunities",
        "path_ar": "/ar/الفرص-والمشاريع",
        "label": {"ar": "الفرص والمشاريع", "en": "Opportunities & Projects"},
    },
    {
        "key": "services",
        "path": "/services",
        "path_ar": "/ar/خدمات-الأعمال",
        "label": {"ar": "خدمات الأعمال", "en": "Business Services"},
    },
    {
        "key": "group",
        "path": "/group-companies",
        "path_ar": "/ar/شركات-المجموعة",
        "label": {"ar": "شركات المجموعة", "en": "Group Companies"},
    },
    {
        "key": "about",
        "path": "/about",
        "path_ar": "/ar/عن-القابضة",
        "label": {"ar": "عن القابضة", "en": "About SAFIR Holding"},
    },
    {
        "key": "contact",
        "path": "/contact",
        "path_ar": "/ar/تواصل",
        "label": {"ar": "تواصل", "en": "Contact"},
    },
]

# Top-level page keys and their localized paths, used by the router and sitemap.
PAGE_PATHS: dict[str, dict[str, str]] = {
    "home": {"ar": "/ar", "en": "/"},
    "opportunities": {"ar": "/ar/الفرص-والمشاريع", "en": "/opportunities"},
    "services": {"ar": "/ar/خدمات-الأعمال", "en": "/services"},
    "group": {"ar": "/ar/شركات-المجموعة", "en": "/group-companies"},
    "about": {"ar": "/ar/عن-القابضة", "en": "/about"},
    "contact": {"ar": "/ar/تواصل", "en": "/contact"},
    "list-your-business": {"ar": "/ar/اعرض-شركتك", "en": "/list-your-business"},
}


@dataclass
class PageMeta:
    """Everything the HTML shell needs for one page.

    Built once per page and consumed by both the renderer and the SEO module,
    so a page's title, description, canonical and structured data are defined
    together and cannot disagree.
    """

    route: str
    lang: str
    title: str
    description: str
    canonical_path: str
    alternates: dict[str, str] = field(default_factory=dict)
    robots: str = "index, follow"
    og_type: str = "website"
    breadcrumbs: list[tuple[str, str]] = field(default_factory=list)


def market_label(market: str, lang: str) -> str:
    return MARKET_LABELS.get(market, {}).get(lang, market)


def nav_label(key: str, lang: str) -> str:
    for item in NAV:
        if item["key"] == key:
            return item["label"][lang]
    return key


def market_slug(market: str, lang: str) -> str:
    return MARKET_SLUG_AR.get(market, market) if lang == "ar" else market


def service_def(slug: str) -> dict | None:
    return SERVICES.get(slug)


def localized_service_slug(slug: str, lang: str) -> str:
    service = SERVICES.get(slug)
    if not service:
        return slug
    return service["slug_ar"] if lang == "ar" else service["slug"]


def market_service_path(market: str, slug: str, lang: str) -> str:
    """The public path for a market/service page in the given language.

    Arabic pages live under ``/ar/<market-ar>/<service-ar>``; English pages
    under ``/<market>/<service>``. This keeps one canonical English URL per
    page and a genuine Arabic mirror, which is what the hreflang pair points
    at.
    """
    service_slug = localized_service_slug(slug, lang)
    if lang == "ar":
        return f"/ar/{market_slug(market, 'ar')}/{service_slug}"
    return f"/{market}/{service_slug}"


def all_market_service_pages() -> list[tuple[str, str]]:
    """Every (market, service-slug) combination that has a real page."""
    return [(market, slug) for market in MARKETS for slug in SERVICES]
