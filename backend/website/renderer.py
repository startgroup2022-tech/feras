"""Server-side HTML rendering for the public website.

Pages are rendered on the server so every route is a real, crawlable document
with its own title, description, canonical and hreflang tags -- a JavaScript
single-page app would make the market/service pages far weaker SEO assets.

The renderer is deliberately simple: small functions returning HTML strings,
composed per route. Every interpolated value passes through :func:`e`
(``html.escape``) so no content -- including a database-sourced opportunity
title -- can inject markup.

Arabic is the default language and RTL the default direction; English pages
render with ``dir="ltr"``. The two are separate URLs, not a client-side toggle,
which is what makes the hreflang pairing meaningful.

The layout follows the V2 visitor journey: the visitor starts from a *need*
(services hub / home journey cards), picks a *market* (Bahrain or Saudi), lands
on a dedicated, indexable market/service page and completes the form for that
market. The group companies and the Holding pages exist for trust, never as the
primary navigation.
"""

from __future__ import annotations

import html

from backend.website import content as C
from backend.website import group_companies
from backend.website import seo
from backend.website.content import PageMeta

BRAND_AR = "سفير القابضة"
BRAND_EN = "Safir Holding"


def e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _t(ar: str, en: str, lang: str) -> str:
    return ar if lang == "ar" else en


def _brand(lang: str) -> str:
    return _t(BRAND_AR, BRAND_EN, lang)


def _flag(market: str) -> str:
    return "🇧🇭" if market == "bahrain" else "🇸🇦"


# --------------------------------------------------------------------------
# shell
# --------------------------------------------------------------------------
def _brand_mark() -> str:
    """The fallback logo mark: a navy hexagon with a gold rim and centre.

    Used only until an official logo is uploaded from the admin panel; the
    header swaps this for the uploaded image automatically.
    """
    return (
        '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" '
        'focusable="false" aria-hidden="true">'
        '<path d="M12 1.8 21 6.9v10.2L12 22.2 3 17.1V6.9L12 1.8Z" fill="#DCBE72"/>'
        '<path d="M12 5.1 18.4 8.7v6.6L12 18.9 5.6 15.3V8.7L12 5.1Z" fill="#0A1730"/>'
        '<path d="M12 9.2 15.4 11v2.9L12 15.7 8.6 13.9V11L12 9.2Z" fill="#DCBE72"/>'
        "</svg>"
    )


def _brand_visual(lang: str, branding: dict | None) -> str:
    """The header logo slot: the uploaded logo, or the built-in fallback mark.

    The container has a fixed height and the image is constrained by
    ``object-fit: contain`` with a max width, so a logo of any aspect ratio or
    dimension can never distort or break the header layout.
    """
    logo_url = (branding or {}).get("logo_url")
    if logo_url:
        return (
            '<span class="brand-logo">'
            f'<img src="{e(logo_url)}" alt="{e(_brand(lang))}" '
            'decoding="async" data-brand-logo></span>'
        )
    return f'<span class="brand-mark" data-brand-fallback>{_brand_mark()}</span>'


def _nav_html(meta: PageMeta, branding: dict | None = None) -> str:
    lang = meta.lang
    links = []
    for item in C.NAV:
        path = item["path"] if lang == "en" else item["path_ar"]
        active = ""
        if item["key"] == meta.route or (
            meta.route.startswith("market-service") and item["key"] == "services"
        ):
            active = ' class="is-active" aria-current="page"'
        links.append(f'<a href="{e(path)}"{active}>{e(item["label"][lang])}</a>')

    # Two explicit options so the active language reads as *selected* rather
    # than as a lone label that happens to link elsewhere.
    def option(code: str) -> str:
        current = code == lang
        href = meta.alternates.get(code) or C.PAGE_PATHS["home"][code]
        label = "العربية" if code == "ar" else "English"
        cls = "lang-opt is-on" if current else "lang-opt"
        state = ' aria-current="true"' if current else ""
        return (
            f'<a class="{cls}" href="{e(href)}" hreflang="{e(code)}" '
            f'lang="{e(code)}"{state}>{e(label)}</a>'
        )

    return f"""
<header class="site-header" data-header>
  <div class="container header-inner">
    <a class="brand" href="{e(C.PAGE_PATHS['home'][lang])}" aria-label="{e(_brand(lang))}">
      {_brand_visual(lang, branding)}
      <span class="brand-text">
        <span class="brand-name">{e(_brand(lang))}</span>
        <span class="brand-sub">{e(_t("بوابة البحرين والسعودية", "Bahrain & Saudi Gateway", lang))}</span>
      </span>
    </a>

    <div class="header-menu" id="primary-nav" data-nav>
      <nav class="site-nav" aria-label="{e(_t('التنقل الرئيسي', 'Main navigation', lang))}">
        {' '.join(links)}
      </nav>
    </div>

    <div class="header-actions">
      <div class="lang-switch" role="group"
           aria-label="{e(_t('اختيار اللغة', 'Language selection', lang))}">
        {option("ar")}{option("en")}
      </div>
      <button class="nav-toggle" type="button" aria-expanded="false"
              aria-controls="primary-nav" data-nav-toggle>
        <span class="sr-only">{e(_t("القائمة", "Menu", lang))}</span>
        <span class="nav-toggle-bars" aria-hidden="true"></span>
      </button>
    </div>
  </div>
</header>"""


def _footer_html(meta: PageMeta) -> str:
    lang = meta.lang
    nav_links = "".join(
        f'<li><a href="{e(item["path"] if lang == "en" else item["path_ar"])}">'
        f'{e(item["label"][lang])}</a></li>'
        for item in C.NAV
    )
    services_links = "".join(
        f'<li><a href="{e(C.market_service_path("bahrain", slug, lang))}">'
        f'{e(service["title"][lang])} — {e(C.market_label("bahrain", lang))}</a></li>'
        f'<li><a href="{e(C.market_service_path("saudi", slug, lang))}">'
        f'{e(service["title"][lang])} — {e(C.market_label("saudi", lang))}</a></li>'
        for slug, service in C.SERVICES.items()
    )
    return f"""
<footer class="site-footer">
  <div class="container footer-inner">
    <div class="footer-brand">
      <span class="brand-mark brand-mark-lg">{_brand_mark()}</span>
      <div class="brand-name">{e(_brand(lang))}</div>
      <p class="footer-tag">{e(_t("بوابتك للأعمال والاستثمار في البحرين والسعودية",
                                   "Your business and investment gateway in Bahrain and Saudi Arabia", lang))}</p>
    </div>
    <nav class="footer-nav" aria-label="{e(_t('روابط التذييل', 'Footer links', lang))}">
      <div class="footer-col">
        <h2 class="footer-heading">{e(_t('روابط سريعة', 'Quick links', lang))}</h2>
        <ul>{nav_links}</ul>
      </div>
      <div class="footer-col">
        <h2 class="footer-heading">{e(_t('الخدمات حسب السوق', 'Services by market', lang))}</h2>
        <ul>{services_links}</ul>
      </div>
    </nav>
  </div>
  <div class="container footer-legal">
    <p>&copy; {e(_t('سفير القابضة', 'Safir Holding', lang))} — {e(_t('جميع الحقوق محفوظة', 'All rights reserved', lang))}</p>
    <a href="{e('/' if lang == 'en' else '/ar')}">{e(_t('الرئيسية', 'Home', lang))}</a>
  </div>
</footer>"""


def render_page(meta: PageMeta, body: str, branding: dict | None = None) -> str:
    """Compose a full HTML document for a resolved route."""
    lang = meta.lang
    direction = "rtl" if lang == "ar" else "ltr"
    jsonld = [seo.organization_jsonld(lang)]
    crumbs = seo.breadcrumb_jsonld(meta.breadcrumbs)
    if crumbs:
        jsonld.append(crumbs)
    service_node = seo.service_jsonld(meta)
    if service_node:
        jsonld.append(service_node)
    faq_node = seo.faq_jsonld(meta)
    if faq_node:
        jsonld.append(faq_node)
    jsonld_html = "".join(seo.jsonld_script(node) for node in jsonld)

    return f"""<!DOCTYPE html>
<html lang="{e(lang)}" dir="{e(direction)}">
<head>
{seo.render_meta_tags(meta)}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@300;400;500;600;700&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/website/assets/styles.css">
{jsonld_html}
</head>
<body class="site lang-{e(lang)}">
<a class="skip-link" href="#main">{e(_t('تخطَّ إلى المحتوى', 'Skip to content', lang))}</a>
{_nav_html(meta, branding)}
<main id="main" tabindex="-1">
{body}
</main>
{_footer_html(meta)}
<noscript>
  <div class="container"><p class="noscript-note">{e(_t(
    'يتطلب إرسال النماذج تفعيل JavaScript. يمكنك التواصل معنا عبر بيانات التواصل في صفحة «تواصل».',
    'Submitting forms requires JavaScript. You can reach us using the details on the Contact page.',
    lang))}</p></div>
</noscript>
<script src="/website/assets/app.js" defer></script>
</body>
</html>"""


# --------------------------------------------------------------------------
# shared building blocks
# --------------------------------------------------------------------------
def _icon(name: str) -> str:
    icons = {
        "opportunities": (
            '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M3 7h18v13H3z"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>'
            '<path d="M3 12h18"/></svg>'
        ),
        "formation": (
            '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M3 21h18"/><path d="M6 21V8l6-5 6 5v13"/><path d="M10 21v-5h4v5"/></svg>'
        ),
        "feasibility": (
            '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M4 19V5a2 2 0 0 1 2-2h9l5 5v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2Z"/>'
            '<path d="M8 13h8"/><path d="M8 17h5"/></svg>'
        ),
        "investment": (
            '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/></svg>'
        ),
        "listing": (
            '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M12 5v14"/><path d="M5 12h14"/></svg>'
        ),
        "group": (
            '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M3 21h18"/><path d="M5 21V9l7-5 7 5v12"/><path d="M9 21v-6h6v6"/></svg>'
        ),
        "contact": (
            '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M4 5h16v14H4z"/><path d="m4 6 8 6 8-6"/></svg>'
        ),
        "shield": (
            '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M12 3 5 6v6c0 4 3 7 7 9 4-2 7-5 7-9V6l-7-3Z"/><path d="m9 12 2 2 4-4"/></svg>'
        ),
    }
    return icons.get(name, "")


def _market_choice(
    lang: str, service_slug: str, heading: str | None = None, sub: str | None = None
) -> str:
    """The two market buttons shown inside every service."""
    cards = []
    for market in C.MARKETS:
        label = C.market_label(market, lang)
        path = C.market_service_path(market, service_slug, lang)
        cards.append(
            f"""<a class="market-card" href="{e(path)}">
  <span class="market-flag" aria-hidden="true">{_flag(market)}</span>
  <span class="market-name">{e(label)}</span>
  <span class="market-cta">{e(_t('ابدأ الآن', 'Get started', lang))} <span aria-hidden="true">←</span></span>
</a>"""
        )
    title = heading or _t("اختر السوق", "Choose your market", lang)
    sub_html = f'<p class="section-sub">{e(sub)}</p>' if sub else ""
    return f"""
<section class="section market-choice">
  <div class="container">
    <h2 class="section-title">{e(title)}</h2>
    {sub_html}
    <div class="market-grid">{''.join(cards)}</div>
  </div>
</section>"""


def _service_cards(lang: str) -> str:
    cards = []
    for slug, service in C.SERVICES.items():
        # Each card leads into the market choice for that service, so the
        # visitor always picks a market explicitly.
        target = C.PAGE_PATHS["services"][lang] + "#" + service["slug"]
        cards.append(
            f"""<a class="service-card" href="{e(target)}" data-service="{e(slug)}">
  <span class="service-icon" aria-hidden="true">{_icon(service['icon'])}</span>
  <h3 class="service-title">{e(service['title'][lang])}</h3>
  <p class="service-blurb">{e(service['blurb'][lang])}</p>
  <span class="service-link">{e(_t('اختر السوق', 'Choose market', lang))} <span aria-hidden="true">←</span></span>
</a>"""
        )
    return f'<div class="service-grid">{"".join(cards)}</div>'


def _steps_list(lang: str, steps: list[tuple[str, str]]) -> str:
    return (
        '<ol class="steps">'
        + "".join(
            f'<li><span class="step-title">{e(title)}</span>'
            f'<span class="step-desc">{e(desc)}</span></li>'
            for title, desc in steps
        )
        + "</ol>"
    )


def _steps_section(lang: str, steps: list[tuple[str, str]], heading: str | None = None) -> str:
    if not steps:
        return ""
    title = heading or _t("كيف تسير الخدمة", "How the service works", lang)
    return f"""
<section class="section">
  <div class="container">
    <h2 class="section-title">{e(title)}</h2>
    {_steps_list(lang, steps)}
  </div>
</section>"""


def _faq_block(lang: str, pairs: list[tuple[str, str]]) -> str:
    items = "".join(
        f"""<details class="faq-item">
  <summary>{e(question)}<span class="faq-caret" aria-hidden="true"></span></summary>
  <p>{e(answer)}</p>
</details>"""
        for question, answer in pairs
    )
    return f"""
<section class="section section-alt">
  <div class="container">
    <h2 class="section-title">{e(_t('أسئلة متكررة', 'Frequently asked questions', lang))}</h2>
    <div class="faq">{items}</div>
  </div>
</section>"""


# --------------------------------------------------------------------------
# home
# --------------------------------------------------------------------------
def _home_body(lang: str) -> str:
    journeys = [
        ("opportunities", C.SERVICES["opportunities"], "opportunities"),
        ("company-formation", C.SERVICES["company-formation"], "formation"),
        ("feasibility-study", C.SERVICES["feasibility-study"], "feasibility"),
        ("list-your-business", None, "listing"),
    ]
    cards = []
    for slug, service, icon in journeys:
        if service is None:
            title = _t("اعرض فرصة / شركة", "List Your Business / Opportunity", lang)
            blurb = _t(
                "قدّم مشروعك أو شركتك للشراكة أو الاستحواذ.",
                "Offer your project or company for partnership or acquisition.",
                lang,
            )
            href = C.PAGE_PATHS["list-your-business"][lang]
        else:
            title = service["title"][lang]
            blurb = service["blurb"][lang]
            href = C.PAGE_PATHS["services"][lang] + "#" + service["slug"]
        cards.append(
            f"""<a class="journey-card" href="{e(href)}">
  <span class="journey-icon" aria-hidden="true">{_icon(icon)}</span>
  <h3>{e(title)}</h3>
  <p>{e(blurb)}</p>
  <span class="journey-cta">{e(_t('ابدأ', 'Start', lang))} <span aria-hidden="true">←</span></span>
</a>"""
        )

    trust = [
        ("shield", _t("توجيه داخلي", "Internal routing", lang),
         _t("نوجّه كل طلب إلى الجهة المختصة داخل القابضة دون أن تحتاج لمعرفتها.",
            "We route each request to the responsible team inside the Holding, without you needing to know it.", lang)),
        ("opportunities", _t("سوقان", "Two markets", lang),
         _t("البحرين والمملكة العربية السعودية، بمحتوى ونماذج مناسبة لكل سوق.",
            "Bahrain and Saudi Arabia, with content and forms suited to each market.", lang)),
        ("group", _t("شركات المجموعة", "Group companies", lang),
         _t("شركات قائمة تدعم التنفيذ، وتظهر لبناء الثقة لا للتنقل.",
            "Established companies that support delivery, shown for trust rather than navigation.", lang)),
    ]
    trust_cards = "".join(
        f"""<article class="trust-card">
  <span class="trust-icon" aria-hidden="true">{_icon(icon)}</span>
  <h3>{e(title)}</h3>
  <p>{e(desc)}</p>
</article>"""
        for icon, title, desc in trust
    )

    return f"""
<section class="hero">
  <div class="container hero-inner">
    <div class="hero-copy">
      <p class="hero-eyebrow">{e(_t('بوابة مؤسسية', 'Corporate gateway', lang))}</p>
      <h1 class="hero-title">{e(_brand(lang))}</h1>
      <p class="hero-tagline">
        <span class="hero-tagline-line">{e(_t('بوابتك للأعمال والاستثمار', 'Your business and investment gateway', lang))}</span>
        <span class="hero-tagline-line">{e(_t('في البحرين والسعودية', 'in Bahrain and Saudi Arabia', lang))}</span>
      </p>
      <p class="hero-values">{e(_t('فرص • تأسيس شركات • دراسات جدوى • شراكات',
                                   'Opportunities • Company Formation • Feasibility Studies • Partnerships', lang))}</p>
      <div class="hero-actions">
        <a class="btn btn-primary" href="#choose">{e(_t('ابدأ باختيار ما تحتاجه', 'Start by choosing what you need', lang))}</a>
        <a class="btn btn-ghost" href="{e(C.PAGE_PATHS['opportunities'][lang])}">{e(_t('استعرض الفرص', 'Browse opportunities', lang))}</a>
      </div>
    </div>
    <div class="hero-panel" aria-hidden="true">
      <div class="hero-panel-head">
        <span class="hero-panel-dot"></span>
        {e(_t('سوقان · مسار واحد', 'Two markets · one path', lang))}
      </div>
      <ul class="hero-panel-list">
        <li><span class="hp-flag">🇧🇭</span>{e(C.market_label('bahrain', lang))}</li>
        <li><span class="hp-flag">🇸🇦</span>{e(C.market_label('saudi', lang))}</li>
      </ul>
      <div class="hero-panel-foot">
        <span>{e(_t('تأسيس شركات', 'Company formation', lang))}</span>
        <span>{e(_t('دراسات جدوى', 'Feasibility', lang))}</span>
        <span>{e(_t('فرص واستثمار', 'Opportunities', lang))}</span>
      </div>
    </div>
  </div>
</section>

<section class="section" id="choose">
  <div class="container">
    <h2 class="section-title">{e(_t('ابدأ باختيار ما تحتاجه', 'Start by choosing what you need', lang))}</h2>
    <p class="section-sub">{e(_t('اختر الخدمة، ثم السوق — ونحن نتولى التوجيه داخليًا.',
                                 'Choose a service, then a market — we handle the routing internally.', lang))}</p>
    <div class="journey-grid">{''.join(cards)}</div>
  </div>
</section>

{_market_choice(lang, 'company-formation', _t('اختر السوق لخدماتنا', 'Choose your market', lang),
                _t('لكل سوق صفحة ونموذج خاصان به.', 'Each market has its own page and form.', lang))}

<section class="section">
  <div class="container">
    <h2 class="section-title">{e(_t('لماذا سفير القابضة', 'Why Safir Holding', lang))}</h2>
    <div class="trust-grid">{trust_cards}</div>
  </div>
</section>

{_group_companies_section(lang,
    heading=_t('شركات المجموعة', 'Group Companies', lang),
    intro=_t('تضم محفظتنا شركات في قطاعات متنوعة، تقدم منتجات وخدمات متخصصة للأفراد والأعمال.',
             'Our portfolio spans companies in diverse sectors, offering specialised products and services to individuals and businesses.', lang))}

<section class="section section-alt">
  <div class="container">
    <h2 class="section-title">{e(_t('كيف تعمل البوابة', 'How the gateway works', lang))}</h2>
    {_steps_list(lang, [
        (_t('اختر احتياجك', 'Choose your need', lang),
         _t('ابدأ من الخدمة التي تبحث عنها.', 'Start from the service you are looking for.', lang)),
        (_t('حدّد السوق: البحرين أو السعودية', 'Select the market: Bahrain or Saudi Arabia', lang),
         _t('لكل سوق صفحة ونموذج ومتطلبات خاصة.', 'Each market has its own page, form and requirements.', lang)),
        (_t('أكمل النموذج المناسب', 'Complete the relevant form', lang),
         _t('أسئلة مخصصة للخدمة والسوق.', 'Questions tailored to the service and the market.', lang)),
        (_t('تتواصل معك الجهة المختصة', 'The responsible team contacts you', lang),
         _t('نوجّه الطلب داخليًا ونحدد المصدر والسوق تلقائيًا.', 'We route it internally and record the source and market automatically.', lang)),
    ])}
  </div>
</section>"""


# --------------------------------------------------------------------------
# services hub
# --------------------------------------------------------------------------
def _services_body(lang: str) -> str:
    blocks = []
    for slug, service in C.SERVICES.items():
        if service["form"] is None:
            # Opportunities is a listing, not a form: link to its market pages.
            market_cards = "".join(
                f'<a class="market-card compact" href="{e(C.market_service_path(market, slug, lang))}">'
                f'<span class="market-name">{e(C.market_label(market, lang))}</span>'
                f'<span class="market-cta">{e(_t("استعرض", "Browse", lang))} <span aria-hidden="true">←</span></span></a>'
                for market in C.MARKETS
            )
            market_block = f'<div class="market-grid">{market_cards}</div>'
        else:
            market_block = _market_choice(lang, slug, _t('اختر السوق', 'Choose your market', lang))
            # _market_choice wraps in a section; unwrap its inner grid for
            # embedding inside this service block.
            market_block = market_block.split('<div class="market-grid">', 1)[1]
            market_block = '<div class="market-grid">' + market_block
        blocks.append(
            f"""<article class="service-block" id="{e(service['slug'])}">
  <header class="service-block-head">
    <span class="service-icon" aria-hidden="true">{_icon(service['icon'])}</span>
    <div>
      <h2>{e(service['title'][lang])}</h2>
      <p>{e(service['blurb'][lang])}</p>
    </div>
  </header>
  {market_block}
</article>"""
        )
    return f"""
<section class="page-hero">
  <div class="container">
    <h1>{e(_t('خدمات الأعمال', 'Business Services', lang))}</h1>
    <p>{e(_t('خدمة واحدة في الواجهة — ومسار مخصص لكل سوق.',
             'One service on the surface — a dedicated path for each market.', lang))}</p>
  </div>
</section>
<section class="section">
  <div class="container">
    {''.join(blocks)}
  </div>
</section>"""


# --------------------------------------------------------------------------
# market / service page
# --------------------------------------------------------------------------
def _market_service_body(lang: str, market: str, slug: str) -> str:
    service = C.service_def(slug)
    content = C.service_market_content(slug, market) or {}
    market_name = C.market_label(market, lang)
    other = "en" if lang == "ar" else "ar"
    other_path = C.market_service_path(market, slug, other)

    intro = content.get("intro", {}).get(lang) or C.MARKET_CONTENT[market]["intro"][lang]
    highlights = content.get("highlights", {}).get(lang) or C.MARKET_CONTENT[market]["highlights"][lang]
    deliverables = content.get("deliverables", {}).get(lang, [])
    steps = content.get("steps", {}).get(lang, [])
    faq = content.get("faq", {}).get(lang, [])

    highlights_html = "".join(f"<li>{e(item)}</li>" for item in highlights)
    deliverables_html = (
        '<ul class="check-list">'
        + "".join(f"<li>{e(item)}</li>" for item in deliverables)
        + "</ul>"
        if deliverables
        else ""
    )

    # The form for this page. Opportunities use the interest flow; every other
    # service has its own form (investment now has a dedicated one).
    form_key = service["form"]
    if slug == "opportunities":
        body_section = _opportunities_section(lang, market)
    else:
        body_section = _form_section(lang, form_key, market, service)

    return f"""
<section class="page-hero">
  <div class="container">
    <nav class="crumbs" aria-label="{e(_t('مسار التنقل', 'Breadcrumb', lang))}">
      <a href="{e(C.PAGE_PATHS['home'][lang])}">{e(_t('الرئيسية', 'Home', lang))}</a>
      <span aria-hidden="true">/</span>
      <a href="{e(C.PAGE_PATHS['services'][lang])}">{e(_t('خدمات الأعمال', 'Business Services', lang))}</a>
      <span aria-hidden="true">/</span>
      <span>{e(market_name)}</span>
    </nav>
    <p class="page-hero-eyebrow">{_flag(market)} {e(market_name)}</p>
    <h1>{e(service['title'][lang])} — {e(market_name)}</h1>
    <p class="page-hero-sub">{e(intro)}</p>
    <div class="page-hero-actions">
      <a class="btn btn-primary" href="#form">{e(_t('ابدأ الطلب', 'Start your request', lang))}</a>
      <a class="btn btn-ghost" href="{e(other_path)}" hreflang="{e(other)}" lang="{e(other)}">
        {e(_t('English', 'العربية', lang))}
      </a>
    </div>
  </div>
</section>

<section class="section">
  <div class="container two-col">
    <div>
      <h2 class="section-title">{e(_t('معلومات السوق', 'Market information', lang))}</h2>
      <ul class="highlights">{highlights_html}</ul>
      {deliverables_html}
    </div>
    <div class="aside-card">
      <h3>{e(_t('ماذا يحدث بعد الإرسال؟', 'What happens after you submit?', lang))}</h3>
      <ol class="mini-steps">
        <li>{e(_t('نسجّل طلبك ونحدد السوق والخدمة تلقائيًا.', 'We record your request and classify market and service automatically.', lang))}</li>
        <li>{e(_t('يوجّه الطلب داخليًا إلى الجهة المختصة.', 'The request is routed internally to the responsible team.', lang))}</li>
        <li>{e(_t('يتواصل معك فريقنا لمتابعة التفاصيل.', 'Our team contacts you to follow up on the details.', lang))}</li>
      </ol>
    </div>
  </div>
</section>

{body_section}

{_steps_section(lang, steps)}

{_faq_block(lang, faq) if faq else ''}"""


# --------------------------------------------------------------------------
# forms
# --------------------------------------------------------------------------
_FORM_LABELS: dict[str, dict[str, str]] = {
    "full_name": {"ar": "الاسم", "en": "Full name"},
    "email": {"ar": "البريد الإلكتروني", "en": "Email"},
    "phone": {"ar": "رقم التواصل", "en": "Contact number"},
    "nationality": {"ar": "الجنسية", "en": "Nationality"},
    "company_name": {"ar": "اسم الشركة (إن وُجد)", "en": "Company name (if any)"},
    "message": {"ar": "ملاحظات إضافية", "en": "Additional notes"},
    "desired_activity": {"ar": "النشاط المطلوب", "en": "Desired activity"},
    "number_of_partners": {"ar": "عدد الشركاء", "en": "Number of partners"},
    "investor_type": {"ar": "نوع المستثمر", "en": "Investor type"},
    "needs_office": {"ar": "هل تحتاج عنوانًا / مكتبًا؟", "en": "Do you need an address / office?"},
    "investor_residency": {"ar": "مستثمر محلي / أجنبي", "en": "Local / foreign investor"},
    "legal_entity": {"ar": "نوع الكيان المطلوب إن كان معروفًا", "en": "Desired legal entity (if known)"},
    "target_city": {"ar": "المدينة المستهدفة", "en": "Target city"},
    "project_idea": {"ar": "فكرة المشروع", "en": "Project idea"},
    "sector": {"ar": "القطاع", "en": "Sector"},
    "project_location": {"ar": "موقع المشروع إن وُجد", "en": "Project location (if any)"},
    "approximate_capital": {"ar": "رأس المال التقريبي", "en": "Approximate capital"},
    "project_stage": {"ar": "هل المشروع جديد أم قائم؟", "en": "New or existing project?"},
    "study_type": {"ar": "نوع الدراسة المطلوبة", "en": "Type of study required"},
    "investor_profile": {"ar": "نبذة عن المستثمر", "en": "Investor profile"},
    "subject": {"ar": "الموضوع", "en": "Subject"},
    "inquiry_type": {"ar": "نوع الاستفسار", "en": "Inquiry type"},
    # Business-listing wizard fields.
    "description": {"ar": "نبذة عن النشاط", "en": "Business description"},
    "reason_for_listing": {"ar": "سبب العرض", "en": "Reason for listing"},
    "desired_outcome": {"ar": "المطلوب (بيع / شراكة / استثمار)", "en": "Desired outcome (sale / partnership / investment)"},
    "business_age_years": {"ar": "عمر النشاط (بالسنوات)", "en": "Business age (years)"},
    "value_min": {"ar": "نطاق القيمة — من", "en": "Value range — from"},
    "value_max": {"ar": "نطاق القيمة — إلى", "en": "Value range — to"},
    "consent": {"ar": "أوافق على معالجة بياناتي وفقًا لإشعار الخصوصية.", "en": "I consent to my data being processed in line with the privacy notice."},
    "honeypot": {"ar": "اترك هذا الحقل فارغًا", "en": "Leave this field empty"},
    "submit": {"ar": "إرسال", "en": "Submit"},
}


def _label(key: str, lang: str) -> str:
    return _FORM_LABELS.get(key, {}).get(lang, key)


def _field(
    key: str,
    lang: str,
    *,
    kind: str = "text",
    required: bool = False,
    options: list[tuple[str, str]] | None = None,
    textarea: bool = False,
    full: bool = False,
) -> str:
    label = _label(key, lang)
    req = ' required aria-required="true"' if required else ""
    req_mark = ' <span class="req" aria-hidden="true">*</span>' if required else ""
    wrapper = ' class="field field-full"' if full else ' class="field"'
    fid = f"f-{key}"
    err_id = f"e-{key}"

    if textarea:
        control = (
            f'<textarea id="{e(fid)}" name="{e(key)}"{req} rows="4" '
            f'aria-describedby="{e(err_id)}"></textarea>'
        )
    elif kind == "select" and options:
        opts = "".join(
            f'<option value="{e(value)}">{e(text)}</option>' for value, text in options
        )
        control = (
            f'<select id="{e(fid)}" name="{e(key)}"{req} aria-describedby="{e(err_id)}">'
            f'<option value="" selected disabled>{e(_t("اختر", "Select", lang))}</option>{opts}</select>'
        )
    elif kind == "checkbox":
        return (
            f'<div class="field field-check">'
            f'<input type="checkbox" id="{e(fid)}" name="{e(key)}"{req} aria-describedby="{e(err_id)}">'
            f'<label for="{e(fid)}">{e(label)}{req_mark}</label>'
            f'<p class="field-error" id="{e(err_id)}" role="alert" hidden></p></div>'
        )
    else:
        control = (
            f'<input type="{e(kind)}" id="{e(fid)}" name="{e(key)}"{req} '
            f'aria-describedby="{e(err_id)}" autocomplete="off">'
        )

    return (
        f'<div{wrapper}><label for="{e(fid)}">{e(label)}{req_mark}</label>'
        f'{control}<p class="field-error" id="{e(err_id)}" role="alert" hidden></p></div>'
    )


def _form_section(lang: str, form_key: str, market: str, service: dict | None) -> str:
    """Render the correct form for a market/service page."""
    market_name = C.market_label(market, lang)
    action = f"/api/v1/public/leads/{form_key}"
    title = _t("أكمل الطلب", "Complete your request", lang)

    fields: list[str] = []
    if form_key == "company-formation":
        fields = [
            _field("full_name", lang, required=True),
            _field("nationality", lang, required=True),
            _field("desired_activity", lang, required=True),
            _field("email", lang, kind="email", required=True),
            _field("phone", lang, kind="tel", required=True),
        ]
        if market == "bahrain":
            fields += [
                _field("number_of_partners", lang, kind="number", required=True),
                _field("investor_type", lang, kind="select", required=True, options=[
                    ("individual", _t("فرد", "Individual", lang)),
                    ("company", _t("شركة", "Company", lang)),
                ]),
                _field("needs_office", lang, kind="select", options=[
                    ("yes", _t("نعم", "Yes", lang)),
                    ("no", _t("لا", "No", lang)),
                ]),
            ]
        else:
            fields += [
                _field("investor_residency", lang, kind="select", required=True, options=[
                    ("local", _t("محلي", "Local", lang)),
                    ("foreign", _t("أجنبي", "Foreign", lang)),
                ]),
                _field("legal_entity", lang),
                _field("target_city", lang, required=True),
            ]
    elif form_key == "feasibility":
        fields = [
            _field("full_name", lang, required=True),
            _field("email", lang, kind="email", required=True),
            _field("phone", lang, kind="tel", required=True),
            _field("project_idea", lang, required=True, textarea=True, full=True),
            _field("sector", lang, required=True),
            _field("project_stage", lang, kind="select", required=True, options=[
                ("new", _t("مشروع جديد", "New project", lang)),
                ("existing", _t("مشروع قائم", "Existing project", lang)),
            ]),
            _field("study_type", lang, kind="select", required=True, options=[
                ("feasibility", _t("دراسة جدوى", "Feasibility", lang)),
                ("market", _t("دراسة سوق", "Market", lang)),
                ("financial", _t("دراسة مالية", "Financial", lang)),
                ("technical", _t("دراسة فنية", "Technical", lang)),
            ]),
            _field("approximate_capital", lang, kind="number"),
        ]
        if market == "saudi":
            fields.append(_field("target_city", lang, required=True))
        else:
            fields.append(_field("project_location", lang))
    elif form_key == "investment":
        fields = [
            _field("full_name", lang, required=True),
            _field("email", lang, kind="email", required=True),
            _field("phone", lang, kind="tel", required=True),
            _field("company_name", lang),
            _field("investor_profile", lang, textarea=True, full=True),
            _field("message", lang, textarea=True, full=True),
        ]
    elif form_key == "opportunity-interest":
        # Only reached from an opportunity page, where the listing id is set by
        # the client when the visitor picks a specific opportunity.
        fields = [
            _field("full_name", lang, required=True),
            _field("email", lang, kind="email", required=True),
            _field("phone", lang, kind="tel", required=True),
            _field("company_name", lang),
            _field("investor_profile", lang, textarea=True, full=True),
            _field("message", lang, textarea=True, full=True),
        ]
    elif form_key == "contact":
        fields = [
            _field("full_name", lang, required=True),
            _field("email", lang, kind="email", required=True),
            _field("phone", lang, kind="tel"),
            _field("inquiry_type", lang, kind="select", required=True, options=[
                ("general", _t("استفسار عام", "General inquiry", lang)),
                ("company_formation", _t("تأسيس شركة", "Company formation", lang)),
                ("feasibility", _t("دراسة جدوى", "Feasibility study", lang)),
                ("opportunity", _t("فرصة أو مشروع", "Opportunity or project", lang)),
                ("partnership", _t("شراكة", "Partnership", lang)),
                ("investment", _t("استثمار", "Investment", lang)),
                ("careers", _t("وظائف", "Careers", lang)),
                ("media", _t("إعلام", "Media", lang)),
            ]),
            _field("subject", lang),
            _field("message", lang, required=True, textarea=True, full=True),
        ]

    hidden = (
        f'<input type="hidden" name="market" value="{e(market)}">'
        f'<input type="hidden" name="locale" value="{e(lang)}">'
        f'<input type="hidden" name="service_type" value="{e(form_key)}">'
    )
    # Honeypot: visually and programmatically hidden from real users.
    honeypot = (
        f'<div class="hp" aria-hidden="true">'
        f'<label for="f-honeypot">{e(_label("honeypot", lang))}</label>'
        f'<input type="text" id="f-honeypot" name="honeypot" tabindex="-1" autocomplete="off">'
        f"</div>"
    )

    context_note = _t(
        f"سيُسجَّل هذا الطلب تلقائيًا ضمن سوق {market_name}.",
        f"This request will automatically be recorded under the {market_name} market.",
        lang,
    )

    return f"""
<section class="section section-alt" id="form">
  <div class="container form-wrap">
    <h2 class="section-title">{e(title)}</h2>
    <p class="form-note">{e(context_note)}</p>
    <form class="site-form" data-form="{e(form_key)}" action="{e(action)}" method="post" novalidate>
      {hidden}
      <div class="field-grid">{''.join(fields)}</div>
      {_field("consent", lang, kind="checkbox", required=True)}
      {honeypot}
      <div class="form-actions">
        <button type="submit" class="btn btn-primary" data-submit>{e(_label("submit", lang))}</button>
        <p class="form-status" role="status" aria-live="polite"></p>
      </div>
    </form>
  </div>
</section>"""


# --------------------------------------------------------------------------
# opportunities
# --------------------------------------------------------------------------
def _opportunities_section(lang: str, market: str) -> str:
    market_name = C.market_label(market, lang)
    return f"""
<section class="section" id="opportunities">
  <div class="container">
    <h2 class="section-title">{e(_t('الفرص المتاحة', 'Available opportunities', lang))}</h2>
    <p class="section-sub">{e(_t('لا نعرض معلومات سرية. التفاصيل الحساسة تُشارك بعد تسجيل الاهتمام ومراجعة الطرف المختص.',
                                 'We do not display confidential information. Sensitive details are shared after interest is registered and reviewed by the responsible party.', lang))}</p>
    <div class="opp-list" data-opportunities data-market="{e(market)}">
      <p class="state">{e(_t('جارٍ تحميل الفرص…', 'Loading opportunities…', lang))}</p>
    </div>
    <div class="opp-interest">
      <a class="btn btn-primary" href="#form">{e(_t('أنا مهتم — اطلب التفاصيل', "I'm interested — request details", lang))}</a>
      <p class="muted">{e(_t(f'سيتم تسجيل اهتمامك ضمن سوق {market_name}.',
                               f'Your interest will be recorded under the {market_name} market.', lang))}</p>
    </div>
  </div>
</section>
{_form_section(lang, "opportunity-interest", market, None)}"""


def _opportunities_body(lang: str) -> str:
    cards = []
    for market in C.MARKETS:
        label = C.market_label(market, lang)
        path = C.market_service_path(market, "opportunities", lang)
        cards.append(
            f"""<a class="market-card" href="{e(path)}">
  <span class="market-flag" aria-hidden="true">{_flag(market)}</span>
  <span class="market-name">{e(label)}</span>
  <span class="market-cta">{e(_t('استعرض الفرص', 'Browse opportunities', lang))} <span aria-hidden="true">←</span></span>
</a>"""
        )
    return f"""
<section class="page-hero">
  <div class="container">
    <h1>{e(_t('الفرص والمشاريع', 'Opportunities & Projects', lang))}</h1>
    <p>{e(_t('يدخل المستثمر أولًا ثم يختار السوق.', 'The investor starts here, then chooses a market.', lang))}</p>
  </div>
</section>
<section class="section">
  <div class="container">
    <h2 class="section-title">{e(_t('اختر السوق', 'Choose your market', lang))}</h2>
    <div class="market-grid">{''.join(cards)}</div>
    <p class="muted center">{e(_t('لا نعرض معلومات سرية علنًا. التفاصيل الحساسة تُشارك بعد تسجيل الاهتمام ومراجعة الطرف المختص.',
                                   'We do not display confidential information publicly. Sensitive details are shared after interest is registered and reviewed by the responsible party.', lang))}</p>
  </div>
</section>
<section class="section section-alt">
  <div class="container">
    <h2 class="section-title">{e(_t('لديك فرصة أو شركة للبيع؟', 'Have an opportunity or business to sell?', lang))}</h2>
    <p class="section-sub">{e(_t('اعرض شركتك أو مشروعك على القابضة للبيع أو الشراكة أو الاستثمار.',
                                 'Offer your business or project to the Holding for sale, partnership or investment.', lang))}</p>
    <a class="btn btn-primary" href="{e(C.PAGE_PATHS['list-your-business'][lang])}">{e(_t('اعرض فرصة / شركة', 'List your business / opportunity', lang))}</a>
  </div>
</section>"""


# --------------------------------------------------------------------------
# list your business (multi-step)
# --------------------------------------------------------------------------
def _list_body(lang: str) -> str:
    steps = [
        _t("الدولة", "Country", lang),
        _t("صفة مقدم الطلب", "Applicant capacity", lang),
        _t("نوع الفرصة", "Opportunity type", lang),
        _t("بيانات النشاط", "Business details", lang),
        _t("المطلوب", "Desired outcome", lang),
        _t("إرسال", "Submit", lang),
    ]
    progress = "".join(
        f'<li data-step="{i + 1}"><span class="step-num">{i + 1}</span><span class="step-label">{e(label)}</span></li>'
        for i, label in enumerate(steps)
    )

    return f"""
<section class="page-hero">
  <div class="container">
    <h1>{e(_t('اعرض شركتك أو مشروعك', 'List your business or project', lang))}</h1>
    <p>{e(_t('مسار لجذب المستثمرين وأصحاب الشركات والوسطاء إلى القابضة.',
             'A path bringing investors, business owners and intermediaries to the Holding.', lang))}</p>
  </div>
</section>

<section class="section">
  <div class="container form-wrap">
    <ol class="progress" aria-label="{e(_t('خطوات التقديم', 'Submission steps', lang))}">{progress}</ol>

    <form class="site-form listing-form" data-form="business-listing"
          action="/api/v1/public/leads/business-listing" method="post" novalidate>
      <input type="hidden" name="locale" value="{e(lang)}">

      <fieldset class="form-step" data-step="1">
        <legend>{e(_t('الدولة', 'Country', lang))}</legend>
        <div class="radio-row">
          <label class="radio-card"><input type="radio" name="market" value="bahrain" required>
            <span>🇧🇭 {e(C.market_label('bahrain', lang))}</span></label>
          <label class="radio-card"><input type="radio" name="market" value="saudi" required>
            <span>🇸🇦 {e(C.market_label('saudi', lang))}</span></label>
        </div>
      </fieldset>

      <fieldset class="form-step" data-step="2" hidden>
        <legend>{e(_t('صفة مقدم الطلب', 'Applicant capacity', lang))}</legend>
        <div class="radio-row">
          <label class="radio-card"><input type="radio" name="applicant_capacity" value="owner" required>
            <span>{e(_t('مالك', 'Owner', lang))}</span></label>
          <label class="radio-card"><input type="radio" name="applicant_capacity" value="representative" required>
            <span>{e(_t('ممثل', 'Representative', lang))}</span></label>
          <label class="radio-card"><input type="radio" name="applicant_capacity" value="advisor" required>
            <span>{e(_t('مستشار / وسيط', 'Advisor / Broker', lang))}</span></label>
        </div>
      </fieldset>

      <fieldset class="form-step" data-step="3" hidden>
        <legend>{e(_t('نوع الفرصة', 'Opportunity type', lang))}</legend>
        <div class="radio-row">
          <label class="radio-card"><input type="radio" name="opportunity_type" value="full_sale" required>
            <span>{e(_t('بيع كامل', 'Full Sale', lang))}</span></label>
          <label class="radio-card"><input type="radio" name="opportunity_type" value="partial_sale" required>
            <span>{e(_t('بيع حصة', 'Partial Sale', lang))}</span></label>
          <label class="radio-card"><input type="radio" name="opportunity_type" value="strategic_partner" required>
            <span>{e(_t('شريك استراتيجي', 'Strategic Partner', lang))}</span></label>
          <label class="radio-card"><input type="radio" name="opportunity_type" value="investment" required>
            <span>{e(_t('استثمار', 'Investment', lang))}</span></label>
        </div>
      </fieldset>

      <fieldset class="form-step" data-step="4" hidden>
        <legend>{e(_t('بيانات النشاط', 'Business details', lang))}</legend>
        <div class="field-grid">
          {_field("full_name", lang, required=True)}
          {_field("company_name", lang)}
          {_field("sector", lang)}
          {_field("business_age_years", lang, kind="number")}
          {_field("email", lang, kind="email", required=True)}
          {_field("phone", lang, kind="tel", required=True)}
          {_field("description", lang, required=True, textarea=True, full=True)}
        </div>
      </fieldset>

      <fieldset class="form-step" data-step="5" hidden>
        <legend>{e(_t('المطلوب', 'Desired outcome', lang))}</legend>
        <div class="field-grid">
          {_field("value_min", lang, kind="number")}
          {_field("value_max", lang, kind="number")}
          {_field("reason_for_listing", lang, textarea=True, full=True)}
          {_field("desired_outcome", lang, textarea=True, full=True)}
        </div>
      </fieldset>

      <fieldset class="form-step" data-step="6" hidden>
        <legend>{e(_t('المراجعة والإرسال', 'Review & submit', lang))}</legend>
        <div class="review-box" data-review></div>
        {_field("consent", lang, kind="checkbox", required=True)}
        <div class="hp" aria-hidden="true">
          <label for="f-honeypot">{e(_label("honeypot", lang))}</label>
          <input type="text" id="f-honeypot" name="honeypot" tabindex="-1" autocomplete="off">
        </div>
      </fieldset>

      <div class="form-nav">
        <button type="button" class="btn btn-ghost" data-prev hidden>{e(_t('السابق', 'Back', lang))}</button>
        <button type="button" class="btn btn-primary" data-next>{e(_t('التالي', 'Next', lang))}</button>
        <button type="submit" class="btn btn-primary" data-submit hidden>{e(_label("submit", lang))}</button>
      </div>
      <p class="form-status" role="status" aria-live="polite"></p>
    </form>
  </div>
</section>"""


# --------------------------------------------------------------------------
# group / about / contact
# --------------------------------------------------------------------------
def _company_logo(company: dict, lang: str, *, large: bool = False) -> str:
    """A neutral logo slot.

    Company logos were not supplied in the handoff, so this is deliberately a
    neutral placeholder. It never invents a mark and never carries the word
    "logo" as if it were the real one: it is a labelled empty slot that the
    admin can later replace with an uploaded logo.
    """
    cls = "company-logo company-logo-lg" if large else "company-logo"
    label = _t("الشعار", "Logo", lang)
    return f'<span class="{cls}" aria-hidden="true">{e(label)}</span>'


def _localized_name(company: dict, lang: str) -> str:
    """The company name in ``lang``.

    ``name_en`` is ``null`` for one company in the approved dataset (a legal
    English name was not supplied). The handoff forbids inventing a translation,
    and requires all nine companies to appear in both languages, so the Arabic
    legal name is shown as-is rather than a fabricated English one.
    """
    return company.get("name_" + lang) or company["name_ar"]


def _company_detail_inner(company: dict, lang: str) -> str:
    """The detail body for one company, in the visitor's language.

    Only facts supplied in the handoff are rendered. A ``null`` field is
    omitted entirely -- never shown as an empty value, a dash or a placeholder.
    """
    name = _localized_name(company, lang)
    country = company["country_" + lang]
    area = company["area_" + lang]
    about = company["about_" + lang]
    services = company["services_" + lang]
    card = company["card_" + lang]

    meta_bits = [e(country)]
    if area:
        meta_bits.append(e(area))

    services_html = ""
    if services:
        items = "".join(f"<li>{e(s)}</li>" for s in services)
        services_html = (
            f'<h4 class="company-sub">{e(_t("أبرز الأنشطة والخدمات", "Key activities and services", lang))}</h4>'
            f'<ul class="company-services">{items}</ul>'
        )

    # Contact actions -- each only rendered when the value exists.
    actions = []
    whatsapp = company.get("whatsapp")
    phone = company.get("phone")
    email = company.get("email")
    website = company.get("website")
    if phone:
        # tel: needs the raw digits with a leading +; strip spaces only.
        tel = "+" + "".join(ch for ch in phone if ch.isdigit())
        actions.append(
            f'<a class="company-action" href="tel:{e(tel)}">'
            f'<span class="company-action-label">{e(_t("هاتف", "Phone", lang))}</span>'
            f'<span class="company-action-value" dir="ltr">{e(phone)}</span></a>'
        )
    if whatsapp:
        wa = "+" + "".join(ch for ch in whatsapp if ch.isdigit())
        actions.append(
            f'<a class="company-action" href="https://wa.me/{e(wa.lstrip("+"))}" '
            f'target="_blank" rel="noopener">'
            f'<span class="company-action-label">{e(_t("واتساب", "WhatsApp", lang))}</span>'
            f'<span class="company-action-value" dir="ltr">{e(whatsapp)}</span></a>'
        )
    if email:
        actions.append(
            f'<a class="company-action" href="mailto:{e(email)}">'
            f'<span class="company-action-label">{e(_t("البريد الإلكتروني", "Email", lang))}</span>'
            f'<span class="company-action-value" dir="ltr">{e(email)}</span></a>'
        )
    if website:
        actions.append(
            f'<a class="company-action" href="{e(website)}" target="_blank" rel="noopener">'
            f'<span class="company-action-label">{e(_t("الموقع", "Website", lang))}</span>'
            f'<span class="company-action-value" dir="ltr">{e(website)}</span></a>'
        )
    actions_html = ""
    if actions:
        actions_html = (
            f'<div class="company-actions">{"".join(actions)}</div>'
        )

    return (
        f'{_company_logo(company, lang, large=True)}'
        f'<h3 class="company-name">{e(name)}</h3>'
        f'<p class="company-meta">{" · ".join(meta_bits)}</p>'
        f'<p class="company-about">{e(about)}</p>'
        f'<p class="company-card-text">{e(card)}</p>'
        f'{services_html}'
        f'{actions_html}'
    )


def _group_companies_section(lang: str, *, heading: str, intro: str) -> str:
    """The interactive group-companies component.

    Desktop: a selectable list (names) beside the selected company's detail.
    Mobile (<= 600px): the same component becomes an accordion -- the chosen
    name expands its detail beneath it and the previous one closes. All nine
    names are always visible, with no horizontal scrolling and no filters, as
    the approved handoff requires. The first company is selected by default.
    """
    companies = group_companies.ordered()
    choices = []
    panels = []
    for index, company in enumerate(companies):
        selected = index == 0
        name = _localized_name(company, lang)
        panel_id = f"company-panel-{index}"
        logo = _company_logo(company, lang)
        choices.append(
            f'<button type="button" class="company-choice" data-company-choice '
            f'data-company-index="{index}" aria-expanded="{"true" if selected else "false"}" '
            f'aria-controls="{panel_id}">'
            f'{logo}<span class="company-choice-name">{e(name)}</span>'
            f'</button>'
        )
        panels.append(
            f'<div class="company-detail inline-detail" id="{panel_id}" '
            f'data-company-panel="{index}"{"" if selected else " hidden"}>'
            f'{_company_detail_inner(company, lang)}</div>'
        )

    # The desktop detail panel mirrors the selected company; it is filled by
    # the interaction script and marked aria-live so a keyboard user hears the
    # change. On mobile it is hidden and the inline panels above are used.
    first = companies[0]
    return f"""
<section class="section company-section" id="companies" data-company-selector>
  <div class="container">
    <h2 class="section-title">{e(heading)}</h2>
    <p class="section-sub">{e(intro)}</p>
    <div class="company-list">
      <div class="company-choices" role="group" aria-label="{e(_t('شركات المجموعة', 'Group companies', lang))}">
        {''.join(choices)}
      </div>
      <div class="company-detail desktop-detail" data-company-detail aria-live="polite">
        {_company_detail_inner(first, lang)}
      </div>
      <div class="company-inline">{''.join(panels)}</div>
    </div>
  </div>
</section>"""


def _group_body(lang: str) -> str:
    return f"""
<section class="page-hero">
  <div class="container">
    <h1>{e(_t('شركات المجموعة', 'Group Companies', lang))}</h1>
    <p>{e(_t('تضم محفظتنا شركات في قطاعات متنوعة، تقدم منتجات وخدمات متخصصة للأفراد والأعمال.',
             'Our portfolio spans companies in diverse sectors, offering specialised products and services to individuals and businesses.', lang))}</p>
  </div>
</section>
{_group_companies_section(lang,
    heading=_t('شركات المجموعة', 'Group Companies', lang),
    intro=_t('اختر شركة لعرض نبذتها وقطاعها وبيانات التواصل المتاحة.',
             'Select a company to view its overview, sector and available contact details.', lang))}
<section class="section section-alt">
  <div class="container center">
    <h2 class="section-title">{e(_t('تبحث عن خدمة؟', 'Looking for a service?', lang))}</h2>
    <a class="btn btn-primary" href="{e(C.PAGE_PATHS['services'][lang])}">{e(_t('تصفح خدمات الأعمال', 'Browse business services', lang))}</a>
  </div>
</section>"""


def _about_body(lang: str) -> str:
    pillars = [
        (_t("التنسيق", "Orchestration", lang),
         _t("نربط المستثمرين والشركات والفرص والخدمات المهنية في مسار واحد.",
            "We connect investors, companies, opportunities and professional services in one path.", lang)),
        (_t("الأسواق", "Markets", lang),
         _t("نعمل عبر سوقين: مملكة البحرين والمملكة العربية السعودية.",
            "We operate across two markets: the Kingdom of Bahrain and Saudi Arabia.", lang)),
        (_t("الشفافية", "Clarity", lang),
         _t("نوجّه كل طلب داخليًا إلى الجهة المختصة، دون أن يحتاج الزائر لمعرفة ذلك.",
            "We route each request internally to the responsible team, without the visitor needing to know.", lang)),
    ]
    cards = "".join(
        f'<article class="pillar"><h3>{e(t)}</h3><p>{e(d)}</p></article>'
        for t, d in pillars
    )
    return f"""
<section class="page-hero">
  <div class="container">
    <h1>{e(_t('عن سفير القابضة', 'About Safir Holding', lang))}</h1>
    <p>{e(_t('طبقة تنسيق تربط المستثمرين والشركات والفرص والخدمات في البحرين والسعودية.',
             'An orchestration layer connecting investors, companies, opportunities and services across Bahrain and Saudi Arabia.', lang))}</p>
  </div>
</section>
<section class="section">
  <div class="container prose">
    <p>{e(_t('سفير القابضة كيان ينسّق بين احتياجات السوق والخدمات المهنية والفرص الاستثمارية. لا يقتصر دورنا على عرض الخدمات، بل على فهم احتياج الزائر ثم توجيهه داخليًا إلى الجهة القادرة على تنفيذه في السوق المختار.',
             'Safir Holding coordinates between market needs, professional services and investment opportunities. Our role is not merely to list services, but to understand what a visitor needs and route it internally to the party able to deliver it in the chosen market.', lang))}</p>
  </div>
</section>
<section class="section section-alt">
  <div class="container">
    <div class="pillar-grid">{cards}</div>
  </div>
</section>
<section class="section">
  <div class="container center">
    <h2 class="section-title">{e(_t('ابدأ من احتياجك', 'Start from your need', lang))}</h2>
    <a class="btn btn-primary" href="{e(C.PAGE_PATHS['services'][lang])}">{e(_t('تصفح الخدمات', 'Browse services', lang))}</a>
  </div>
</section>"""


def _contact_body(lang: str) -> str:
    return f"""
<section class="page-hero">
  <div class="container">
    <h1>{e(_t('تواصل معنا', 'Contact us', lang))}</h1>
    <p>{e(_t('اختر السوق ونوع الاستفسار، وسيتواصل معك الفريق المختص.',
             'Choose your market and inquiry type, and the responsible team will get back to you.', lang))}</p>
  </div>
</section>
{_form_section(lang, "contact", "bahrain", None)}"""


def not_found_body(lang: str) -> str:
    return f"""
<section class="page-hero">
  <div class="container center">
    <h1>{e(_t('الصفحة غير موجودة', 'Page not found', lang))}</h1>
    <p>{e(_t('تعذّر العثور على الصفحة المطلوبة. يمكنك العودة إلى الرئيسية أو تصفح الخدمات.',
             'We could not find the page you requested. You can return home or browse the services.', lang))}</p>
    <div class="page-hero-actions" style="justify-content:center">
      <a class="btn btn-primary" href="{e(C.PAGE_PATHS['home'][lang])}">{e(_t('الرئيسية', 'Home', lang))}</a>
      <a class="btn btn-ghost" href="{e(C.PAGE_PATHS['services'][lang])}">{e(_t('الخدمات', 'Services', lang))}</a>
    </div>
  </div>
</section>"""


# --------------------------------------------------------------------------
# dispatch
# --------------------------------------------------------------------------
def _body_for(meta: PageMeta) -> str:
    route = meta.route
    lang = meta.lang
    if route == "home":
        return _home_body(lang)
    if route.startswith("market-service:"):
        _, market, slug = route.split(":", 2)
        return _market_service_body(lang, market, slug)
    if route == "services":
        return _services_body(lang)
    if route == "opportunities":
        return _opportunities_body(lang)
    if route == "list-your-business":
        return _list_body(lang)
    if route == "group":
        return _group_body(lang)
    if route == "about":
        return _about_body(lang)
    if route == "contact":
        return _contact_body(lang)
    return not_found_body(lang)


def render(meta: PageMeta, branding: dict | None = None) -> str:
    """Render a full page for a resolved route."""
    return render_page(meta, _body_for(meta), branding)


__all__ = ["render", "render_page", "not_found_body", "e"]
