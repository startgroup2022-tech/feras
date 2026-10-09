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
from datetime import datetime, timezone

from backend.website import content as C
from backend.website import group_companies
from backend.website import seo
from backend.website.content import PageMeta

BRAND_AR = "ستارت أب سفير القابضة"
BRAND_EN = "Start Upsphere Holding"

# The original owner-supplied logo, shipped as a static asset (handoff §1,
# assets/ASSETS.md). It is never recoloured or re-proportioned; the header
# constrains it with ``object-fit: contain`` so no display size distorts it.
BRAND_LOGO_URL = "/website/assets/holding-logo.png"

# The owner-selected visual reference for the hero (handoff assets/ASSETS.md).
# Used as a background image only; the layout must remain legible if it fails
# to load, so the hero carries its own background colour underneath.
BRAND_HERO_URL = "/website/assets/bahrain-bay.jpg"


def _current_year() -> int:
    """The real copyright year, computed per request rather than hard-coded."""
    return datetime.now(timezone.utc).year


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


def _brand_visual(lang: str, branding: dict | None, logo_url: str | None = None) -> str:
    """The header logo slot: the uploaded logo, or the shipped original mark.

    The admin-uploaded logo (CMS) wins when present; otherwise the original
    owner-supplied logo ships as a static asset (handoff assets/ASSETS.md). The
    container has a fixed height and the image is constrained by
    ``object-fit: contain`` with a max width, so a logo of any aspect ratio or
    dimension can never distort or break the header layout.
    """
    logo_url = logo_url or (branding or {}).get("logo_url") or BRAND_LOGO_URL
    return (
        '<span class="brand-logo">'
        f'<img src="{e(logo_url)}" alt="{e(_brand(lang))}" '
        'decoding="async" data-brand-logo></span>'
    )


def _brand_logo_img(lang: str) -> str:
    """An instance of the shipped original logo, for the footer.

    Uses the same static asset as the header so the identity is consistent and
    the owner-supplied mark is never redrawn or recoloured (handoff §1).
    """
    return (
        f'<img src="{e(BRAND_LOGO_URL)}" alt="{e(_brand(lang))}" '
        'decoding="async" data-brand-logo>'
    )


def _nav_html(meta: PageMeta, branding: dict | None = None, cms=None) -> str:
    lang = meta.lang
    logo_url = None
    brand_name = _brand(lang)
    if cms is not None and cms.settings:
        logo_url = cms.settings.get("logo_url")
        brand_name = (cms.settings.get("site_name") or {}).get(lang) or brand_name
    links = []
    # A CMS header menu, when configured, replaces the built-in links but points
    # only at validated destinations. An empty menu falls back to the V2 nav.
    source = cms.header_menu if (cms is not None and cms.header_menu) else None
    if source:
        for item in source:
            href = item["url"]
            label = item["label"].get(lang) or item["label"].get("ar") or href
            active = ""
            if href == meta.canonical_path:
                active = ' class="is-active" aria-current="page"'
            links.append(f'<a href="{e(href)}"{active}>{e(label)}</a>')
    else:
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
    <a class="brand" href="{e(C.PAGE_PATHS['home'][lang])}" aria-label="{e(brand_name)}">
      {_brand_visual(lang, branding, logo_url)}
    </a>

    <div class="header-menu" id="primary-nav" data-nav>
      <nav class="site-nav" aria-label="{e(_t('التنقل الرئيسي', 'Main navigation', lang))}">
        {' '.join(links)}
      </nav>
      <div class="menu-lang">
        <div class="lang-switch" role="group"
             aria-label="{e(_t('اختيار اللغة', 'Language selection', lang))}">
          {option("ar")}{option("en")}
        </div>
      </div>
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
</header>
<div class="nav-backdrop" data-nav-backdrop hidden></div>"""


def _footer_html(meta: PageMeta, cms=None) -> str:
    lang = meta.lang
    brand_name = _brand(lang)
    contact_lines = ""
    if cms is not None and cms.settings:
        brand_name = (cms.settings.get("site_name") or {}).get(lang) or brand_name
        bits = []
        if cms.settings.get("contact_email"):
            bits.append(
                f'<li>✉ <a href="mailto:{e(cms.settings["contact_email"])}">'
                f'{e(cms.settings["contact_email"])}</a></li>'
            )
        if cms.settings.get("contact_phone"):
            bits.append(f'<li>☎ {e(cms.settings["contact_phone"])}</li>')
        if cms.settings.get("whatsapp_number"):
            bits.append(f'<li>WhatsApp: {e(cms.settings["whatsapp_number"])}</li>')
        if bits:
            contact_lines = (
                f'<div class="footer-col"><h2 class="footer-heading">'
                f'{e(_t("تواصل", "Contact", lang))}</h2><ul>{"".join(bits)}</ul></div>'
            )
    if cms is not None and cms.footer_menu:
        nav_links = "".join(
            f'<li><a href="{e(item["url"])}">'
            f'{e(item["label"].get(lang) or item["label"].get("ar") or item["url"])}</a></li>'
            for item in cms.footer_menu
        )
    else:
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
    holding = C.HOLDING
    holding_name = holding["name_ar"] if lang == "ar" else holding["name_en"]
    holding_address = holding["address_ar"] if lang == "ar" else holding["address_en"]
    holding_tagline = holding["tagline_ar"] if lang == "ar" else holding["tagline_en"]
    return f"""
<footer class="site-footer">
  <div class="container footer-inner">
    <div class="footer-brand">
      <span class="brand-logo brand-logo-lg">{_brand_logo_img(lang)}</span>
      <div class="brand-name">{e(holding_name)}</div>
      <p class="footer-tag">{e(holding_tagline)}</p>
    </div>
    <nav class="footer-nav" aria-label="{e(_t('روابط التذييل', 'Footer links', lang))}">
      <div class="footer-col">
        <h2 class="footer-heading">{e(_t('الروابط السريعة', 'Quick links', lang))}</h2>
        <ul>{nav_links}</ul>
      </div>
      <div class="footer-col">
        <h2 class="footer-heading">{e(_t('الخدمات حسب السوق', 'Services by market', lang))}</h2>
        <ul>{services_links}</ul>
      </div>
      <div class="footer-col">
        <h2 class="footer-heading">{e(_t('تواصل معنا', 'Contact us', lang))}</h2>
        <ul>
          <li>{e(holding_address)}</li>
          <li><a href="tel:{e(holding['phone_href'])}" dir="ltr">{e(holding['phone'])}</a></li>
          <li><a href="mailto:{e(holding['email'])}">{e(holding['email'])}</a></li>
        </ul>
      </div>
      {contact_lines}
    </nav>
  </div>
  <div class="container footer-legal">
    <p>&copy; {_current_year()} {e(holding_name)} {e(_t('جميع الحقوق محفوظة', 'All rights reserved', lang))}</p>
    <p class="footer-legal-links">
      <a href="{e(C.PAGE_PATHS['privacy'][lang])}">{e(_t('سياسة الخصوصية', 'Privacy Policy', lang))}</a>
      <span aria-hidden="true"> · </span>
      <a href="{e(C.PAGE_PATHS['terms'][lang])}">{e(_t('الشروط والأحكام', 'Terms & Conditions', lang))}</a>
    </p>
  </div>
  <a class="whatsapp-float" href="https://wa.me/{e(str(holding['whatsapp']))}" rel="noopener noreferrer" target="_blank">
    {e(_t('واتساب القابضة', 'Holding WhatsApp', lang))}
  </a>
</footer>"""


def _brand_logo_img(lang: str) -> str:
    """The footer instance of the original logo (shared asset)."""
    return (
        f'<img src="{e(BRAND_LOGO_URL)}" alt="{e(_brand(lang))}" '
        'decoding="async" data-brand-logo>'
    )


def render_page(meta: PageMeta, body: str, branding: dict | None = None, cms=None) -> str:
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
{_nav_html(meta, branding, cms)}
<main id="main" tabindex="-1">
{body}
</main>
{_footer_html(meta, cms)}
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
def _home_body(lang: str, cms_companies=None) -> str:
    """The approved home page: Hero → About → Companies → Opportunities → Help.

    Order and copy follow the handoff exactly (SPECIFICATION.md §3 الرئيسية).
    The hero carries the fixed name/definition and a single "Group Companies"
    button; the company section is the interactive selector; the opportunities
    section shows the latest published listings (the client fills them from the
    API) and the group-services form closes the page.
    """
    text = C.PAGE_TEXT["home"]
    holding = C.HOLDING
    name = holding["name_ar"] if lang == "ar" else holding["name_en"]

    return f"""
<section class="hero hero-home" id="home-hero" style="background-image:linear-gradient(100deg, rgba(10,23,48,.94) 0%, rgba(10,23,48,.80) 46%, rgba(10,23,48,.55) 100%), linear-gradient(180deg, rgba(10,23,48,.30) 0%, rgba(10,23,48,.10) 45%, rgba(10,23,48,.45) 100%), url('{e(BRAND_HERO_URL)}')">
  <div class="container hero-inner">
    <div class="hero-copy">
      <h1 class="hero-title">{e(name)}</h1>
      <p class="hero-intro">{e(text['intro'][lang])}</p>
      <div class="hero-actions">
        <a class="btn btn-primary" href="{e(C.PAGE_PATHS['group'][lang])}">{e(_t('شركات المجموعة', 'Group Companies', lang))}</a>
      </div>
    </div>
  </div>
</section>

<section class="section about-teaser">
  <div class="container narrow center">
    <h2 class="section-title">{e(_t('من نحن', 'About Us', lang))}</h2>
    <p class="section-lead">{e(text['about_teaser'][lang])}</p>
    <a class="btn btn-ghost" href="{e(C.PAGE_PATHS['about'][lang])}">{e(_t('اعرف المزيد', 'Learn More', lang))}</a>
  </div>
</section>

{_group_companies_section(lang,
    heading=_t('شركات المجموعة', 'Group Companies', lang),
    intro=_t('تضم محفظتنا شركات في قطاعات متنوعة، تقدم منتجات وخدمات متخصصة للأفراد والأعمال.',
             'Our portfolio brings together companies across diverse sectors, offering specialised products and services to individuals and businesses.', lang),
    cms_companies=cms_companies)}

<section class="section section-alt" id="opportunities">
  <div class="container">
    <h2 class="section-title">{e(_t('الفرص التجارية', 'Business Opportunities', lang))}</h2>
    <p class="section-lead">{e(C.PAGE_TEXT['opportunities']['intro'][lang])}</p>
    <div class="opp-list" data-opportunities data-limit="3">
      <p class="state">{e(_t('جارٍ تحميل الفرص…', 'Loading opportunities…', lang))}</p>
    </div>
    <div class="opp-cta">
      <a class="btn btn-primary" href="{e(C.PAGE_PATHS['opportunities'][lang])}">{e(_t('عرض جميع الفرص', 'View All Opportunities', lang))}</a>
      <a class="btn btn-ghost" href="{e(C.PAGE_PATHS['list-your-business'][lang])}">{e(_t('اعرض مشروعك', 'Submit Your Business', lang))}</a>
    </div>
  </div>
</section>

<section class="section" id="help">
  <div class="container narrow center">
    <h2 class="section-title">{e(_t('كيف يمكننا مساعدتك؟', 'How Can We Help?', lang))}</h2>
    <p class="section-lead">{e(text['help_intro'][lang])}</p>
  </div>
</section>

{_form_section(lang, "group-service", "gulf", None, heading=_t('بيانات الطلب', 'Request details', lang))}"""


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
    # Group-services ("كيف يمكننا مساعدتك؟") form (handoff §4).
    "phone_intl": {"ar": "رقم الهاتف مع مفتاح الدولة", "en": "Phone number with country code"},
    "service": {"ar": "الخدمة", "en": "Service"},
    "country": {"ar": "الدولة", "en": "Country"},
    # Careers form (handoff §3 الوظائف).
    "residence_country": {"ar": "دولة الإقامة", "en": "Country of residence"},
    "residence_country_other": {"ar": "اسم الدولة", "en": "Country name"},
    "city": {"ar": "المدينة", "en": "City"},
    "job_title": {"ar": "المسمى الوظيفي / مجال التخصص", "en": "Job title / field of specialisation"},
    "years_experience": {"ar": "سنوات الخبرة", "en": "Years of experience"},
    "preferred_company": {"ar": "الشركة التي ترغب في العمل لديها", "en": "Company you would like to work for"},
    "cv": {"ar": "رفع السيرة الذاتية", "en": "Upload your CV"},
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
    accept: str | None = None,
    key_alias: str | None = None,
    attrs: str = "",
    multiple: bool = False,
    label_ar: str | None = None,
    label_en: str | None = None,
    hint_ar: str | None = None,
    hint_en: str | None = None,
) -> str:
    if label_ar is not None or label_en is not None:
        label = (label_en if lang == "en" else label_ar) or _label(key_alias or key, lang)
    else:
        label = _label(key_alias or key, lang)
    hint = (hint_en if lang == "en" else hint_ar) if (hint_ar or hint_en) else None
    req = ' required aria-required="true"' if required else ""
    req_mark = ' <span class="req" aria-hidden="true">*</span>' if required else ""
    wrapper = ' class="field field-full"' if full else ' class="field"'
    extra = f" {attrs}" if attrs else ""
    fid = f"f-{key}"
    err_id = f"e-{key}"

    if textarea:
        control = (
            f'<textarea id="{e(fid)}" name="{e(key)}"{req} rows="4"{extra} '
            f'aria-describedby="{e(err_id)}"></textarea>'
        )
    elif kind == "select" and options:
        opts = "".join(
            f'<option value="{e(value)}">{e(text)}</option>' for value, text in options
        )
        placeholder = _t("اختر", "Select", lang)
        control = (
            f'<select id="{e(fid)}" name="{e(key)}"{req}{extra} aria-describedby="{e(err_id)}">'
            f'<option value="" selected disabled>{e(placeholder)}</option>{opts}</select>'
        )
    elif kind == "file":
        accept_attr = f' accept="{e(accept)}"' if accept else ""
        multiple_attr = " multiple" if multiple else ""
        control = (
            f'<input type="file" id="{e(fid)}" name="{e(key)}"{req}{accept_attr}{multiple_attr}{extra} '
            f'aria-describedby="{e(err_id)}">'
        )
    elif kind == "checkbox":
        return (
            f'<div class="field field-check"{extra}>'
            f'<input type="checkbox" id="{e(fid)}" name="{e(key)}"{req} aria-describedby="{e(err_id)}">'
            f'<label for="{e(fid)}">{e(label)}{req_mark}</label>'
            f'<p class="field-error" id="{e(err_id)}" role="alert" hidden></p></div>'
        )
    else:
        control = (
            f'<input type="{e(kind)}" id="{e(fid)}" name="{e(key)}"{req}{extra} '
            f'aria-describedby="{e(err_id)}" autocomplete="off">'
        )

    hint_html = f'<p class="field-hint">{e(hint)}</p>' if hint else ""
    return (
        f'<div{wrapper}><label for="{e(fid)}">{e(label)}{req_mark}</label>'
        f'{hint_html}{control}<p class="field-error" id="{e(err_id)}" role="alert" hidden></p></div>'
    )


def _form_section(
    lang: str, form_key: str, market: str, service: dict | None, *, heading: str | None = None
) -> str:
    """Render the correct form for a market/service page.

    ``heading`` overrides the form's own title so a page whose hero already
    carries the section name can label the form functionally (item 17: avoid a
    duplicate heading).
    """
    action = f"/api/v1/public/leads/{form_key}"
    titles = {
        "group-service": _t("كيف يمكننا مساعدتك؟", "How Can We Help?", lang),
        "careers": _t("انضم إلى فريق ستارت أب سفير", "Join the Startup Safeer Team", lang),
    }
    title = heading or titles.get(form_key) or _t("أكمل الطلب", "Complete your request", lang)

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
    elif form_key == "group-service":
        # Handoff §4 "كيف يمكننا مساعدتك؟": name, phone (with country code),
        # email, one of six services and one of seven countries. No market: the
        # country the visitor picks is the answer, and the Holding routes the
        # enquiry internally.
        service_opts = [(s["id"], s[lang]) for s in C.SERVICE_OPTIONS]
        country_opts = [(c["id"], c[lang]) for c in C.SERVICE_COUNTRIES]
        fields = [
            _field("full_name", lang, required=True),
            _field("phone", lang, kind="tel", required=True, key_alias="phone_intl"),
            _field("email", lang, kind="email", required=True),
            _field("service", lang, kind="select", required=True, options=service_opts),
            _field("country", lang, kind="select", required=True, options=country_opts),
            _field("message", lang, textarea=True, full=True),
        ]
    elif form_key == "careers":
        # Handoff §3 الوظائف: no vacancies list, one form; CV + notes span the
        # form width. Residence country is a free list (not the service-country
        # restriction). The preferred company is one of the nine group
        # companies plus "any suitable opportunity".
        from backend.website import group_companies as G

        company_opts = [("", _t("أي فرصة مناسبة", "Any suitable opportunity", lang))]
        company_opts += [
            (c["id"], _localized_name(c, lang)) for c in G.ordered()
        ]
        country_opts = [(c["id"], c[lang]) for c in C.SERVICE_COUNTRIES]
        country_opts.append(("other", _t("دولة أخرى", "Other country", lang)))
        fields = [
            _field("full_name", lang, required=True),
            _field("phone", lang, kind="tel", required=True),
            _field("email", lang, kind="email", required=True),
            _field("residence_country", lang, kind="select", required=True, options=country_opts),
            _field(
                "residence_country_other",
                lang,
                attrs='data-other-for="residence_country" hidden',
            ),
            _field("city", lang),
            _field("job_title", lang, required=True),
            _field("years_experience", lang, required=True),
            _field("preferred_company", lang, kind="select", options=company_opts),
            _field("cv", lang, kind="file", required=True, full=True, accept=".pdf,.doc,.docx",
                   hint_ar="الصيغ المقبولة: PDF أو DOC أو DOCX، وبحد أقصى 10 ميجابايت. تبقى السيرة لدى القابضة ولا تُعرض للعامة.",
                   hint_en="Accepted formats: PDF, DOC or DOCX, up to 10 MB. Your CV stays with the Holding and is never shown publicly."),
            _field("message", lang, textarea=True, full=True),
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

    # The careers form carries a CV, so it must submit as multipart. The other
    # forms send JSON, which lets the client surface per-field server errors.
    multipart = form_key == "careers"
    enctype = ' enctype="multipart/form-data"' if multipart else ""
    multipart_attr = ' data-multipart="1"' if multipart else ""

    if multipart:
        context_note = _t(
            "تُرسل السيرة الذاتية إلى القابضة، ونتواصل معك عند توفر فرصة مناسبة.",
            "Your CV is sent to the Holding, and we contact you when a suitable opportunity arises.",
            lang,
        )
    elif form_key == "group-service":
        # The visitor's chosen country is the answer; there is no market to
        # name here (item 15 removed the internal "recorded under gulf" note).
        context_note = _t(
            "سنوجّه طلبك إلى الجهة المختصة داخل شركات المجموعة وفق الخدمة والدولة المختارتين.",
            "We will direct your request to the responsible team within our group, based on the service and country you choose.",
            lang,
        )
    else:
        context_note = _t(
            "سنوجّه طلبك إلى الجهة المختصة داخل شركات المجموعة.",
            "We will direct your request to the responsible team within our group.",
            lang,
        )

    return f"""
<section class="section section-alt" id="form">
  <div class="container form-wrap">
    <h2 class="section-title">{e(title)}</h2>
    <p class="form-note">{e(context_note)}</p>
    <form class="site-form" data-form="{e(form_key)}"{multipart_attr} action="{e(action)}" method="post"{enctype} novalidate>
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
    <p class="listing-notice">{e(_t('المعلومات مقدمة من صاحب المشروع، ونشرها لا يمثل ضمانًا أو توصية استثمارية من الإدارة.',
                                        'Information is provided by the project owner; publishing it is not a guarantee or an investment recommendation from the management.', lang))}</p>
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
    <p>{e(_t('استعرض المشاريع المعروضة للبيع في دول الخليج.', 'Browse businesses offered for sale across the Gulf.', lang))}</p>
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
    <h2 class="section-title">{e(_t('اعرض مشروعك', 'Submit Your Business', lang))}</h2>
    <p class="section-sub">{e(_t('أرسل بيانات مشروعك لعرضه للبيع في دول الخليج، بعد المراجعة والموافقة.',
                                 'Send your project details to be listed for sale in the Gulf, after review and approval.', lang))}</p>
    <a class="btn btn-primary" href="{e(C.PAGE_PATHS['list-your-business'][lang])}">{e(_t('اعرض مشروعك', 'Submit Your Business', lang))}</a>
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

    <form class="site-form listing-form" data-form="business-listing" data-multipart="1"
          action="/api/v1/public/leads/business-listing" method="post"
          enctype="multipart/form-data" novalidate>
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
        <div class="field-grid">
          {_field("proof", lang, kind="file", full=True, accept=".pdf,.png,.jpg,.jpeg",
                  label_ar="إثبات العلاقة بالمشروع (اختياري)",
                  label_en="Proof of relationship to the project (optional)",
                  hint_ar="مستند يوضح صفتك تجاه المشروع (ملاك، تمثيل، أو وساطة). لا يُنشر إطلاقًا، ويُستخدم للمراجعة الداخلية فقط. حتى 10 ميجابايت (PDF أو صورة).",
                  hint_en="A document evidencing your capacity towards the project (owner, representative or intermediary). Never published; used for internal review only. Up to 10 MB (PDF or image).")}
          {_field("photos", lang, kind="file", full=True, multiple=True,
                  accept=".png,.jpg,.jpeg,.webp",
                  label_ar="صور المشروع (اختيارية)",
                  label_en="Project photos (optional)",
                  hint_ar="حتى 10 صور بصيغة PNG أو JPG أو WebP، وبحد أقصى 5 ميجابايت للصورة. تظهر فقط بعد الموافقة على الإعلان ونشره.",
                  hint_en="Up to 10 images in PNG, JPG or WebP, at most 5 MB each. Shown only after the listing is approved and published.")}
        </div>
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
    """The company logo, or a neutral placeholder when none is set.

    Company logos were not supplied in the handoff, so an unset logo is a
    labelled empty slot -- never an invented mark. The admin can upload a real
    logo from Website Management, which then renders here.
    """
    cls = "company-logo company-logo-lg" if large else "company-logo"
    logo_url = company.get("logo")
    if logo_url:
        return (
            f'<span class="{cls}"><img src="{e(logo_url)}" '
            f'alt="{e(_localized_name(company, lang))}" loading="lazy"></span>'
        )
    label = _t("الشعار", "Logo", lang)
    return f'<span class="{cls}" aria-hidden="true">{e(label)}</span>'


def _cms_company_record(company: dict) -> dict:
    """Shape a CMS company context into the flat record the renderer expects.

    Missing English copy falls back to Arabic (never a fabricated translation),
    matching the handoff rule that already governs the ``name_en: null`` case.
    """
    name_ar = company["name"]["ar"]
    name_en = company["name"].get("en") or name_ar
    about_ar = company["description"].get("ar") or ""
    about_en = company["description"].get("en") or about_ar
    card_ar = (company.get("activity") or {}).get("ar")
    card_en = (company.get("activity") or {}).get("en") or card_ar
    country = company.get("country") or ""
    return {
        "id": company["slug"],
        "name_ar": name_ar,
        "name_en": name_en,
        "country_ar": country,
        "country_en": country,
        "area_ar": (company.get("location") or {}).get("ar"),
        "area_en": (company.get("location") or {}).get("en"),
        "phone": company.get("phone"),
        "email": company.get("email"),
        "whatsapp": company.get("whatsapp"),
        "website": company.get("website"),
        "logo": company.get("logo_url"),
        "about_ar": about_ar,
        "about_en": about_en,
        "services_ar": [],
        "services_en": [],
        "card_ar": card_ar,
        "card_en": card_en,
    }


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


def _group_companies_section(lang: str, *, heading: str, intro: str, cms_companies=None) -> str:
    """The interactive group-companies component.

    Desktop: a selectable list (names) beside the selected company's detail.
    Mobile (<= 600px): the same component becomes an accordion -- the chosen
    name expands its detail beneath it and the previous one closes. All nine
    names are always visible, with no horizontal scrolling and no filters, as
    the approved handoff requires. The first company is selected by default.
    """
    if cms_companies:
        companies = [_cms_company_record(c) for c in cms_companies]
    else:
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


def _group_body(lang: str, cms_companies=None) -> str:
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
             'Select a company to view its overview, sector and available contact details.', lang),
    cms_companies=cms_companies)}
<section class="section section-alt">
  <div class="container center">
    <h2 class="section-title">{e(_t('تبحث عن خدمة؟', 'Looking for a service?', lang))}</h2>
    <a class="btn btn-primary" href="{e(C.PAGE_PATHS['services'][lang])}">{e(_t('تصفح خدمات الأعمال', 'Browse business services', lang))}</a>
  </div>
</section>"""


def _about_body(lang: str) -> str:
    """The approved about page: intro → role → portfolio → growth → links.

    Copy is the handoff's approved Arabic and reviewed English
    (content/ARABIC.md, ENGLISH.md). On desktop the heading sits beside the
    text; the CSS handles the mobile stack. There is no profile download until
    the owner supplies the document.
    """
    text = C.PAGE_TEXT["about"]

    row = lambda heading_ar, heading_en, body: f"""
<section class="about-row">
  <div class="container about-row-inner">
    <h2 class="about-row-heading">{e(_t(heading_ar, heading_en, lang))}</h2>
    <div class="about-row-body">{body}</div>
  </div>
</section>"""

    portfolio = "".join(
        f"<p>{e(text[k][lang])}</p>" for k in ("portfolio_1", "portfolio_2")
    )
    grow = "".join(
        f"<p>{e(text[k][lang])}</p>" for k in ("grow_1", "grow_2")
    )

    return f"""
<section class="page-hero page-hero-intro">
  <div class="container narrow">
    <h1>{e(_t('من نحن', 'About Us', lang))}</h1>
    <p class="section-lead">{e(text['intro'][lang])}</p>
  </div>
</section>

{row("دورنا داخل المجموعة", "Our Role Within the Group", f"<p>{e(text['role'][lang])}</p>")}
{row("محفظتنا الحالية", "Our Current Portfolio", portfolio)}
{row("كيف ننمو", "How We Grow", grow)}

<section class="section">
  <div class="container center">
    <div class="page-hero-actions" style="justify-content:center">
      <a class="btn btn-primary" href="{e(C.PAGE_PATHS['group'][lang])}">{e(_t('شركات المجموعة', 'Group Companies', lang))}</a>
      <a class="btn btn-ghost" href="{e(C.PAGE_PATHS['contact'][lang])}">{e(_t('تواصل معنا', 'Contact Us', lang))}</a>
    </div>
  </div>
</section>"""


def _contact_body(lang: str) -> str:
    """The approved contact page: holding details and WhatsApp.

    The handoff (§3 التواصل) specifies contact details with no form and no
    opening hours, and the map is hidden until a link is confirmed -- so a
    neutral placeholder stands in for it rather than an embedded map.
    """
    holding = C.HOLDING
    name = holding["name_ar"] if lang == "ar" else holding["name_en"]
    address = holding["address_ar"] if lang == "ar" else holding["address_en"]
    legum = "START UPSPHERE HOLDING CO W.L.L"
    return f"""
<section class="page-hero page-hero-intro">
  <div class="container narrow">
    <h1>{e(_t('تواصل معنا', 'Contact Us', lang))}</h1>
    <p class="section-lead">{e(C.PAGE_TEXT['contact']['intro'][lang])}</p>
  </div>
</section>

<section class="section">
  <div class="container two-col contact-grid">
    <div class="contact-card">
      <h2 class="section-title">{e(name)}</h2>
      <p class="contact-legal" dir="ltr">{e(legum)}</p>
      <p><strong>{e(_t('المقر الرئيسي:', 'Head Office:', lang))}</strong> {e(address)}</p>
      <p><strong>{e(_t('الهاتف:', 'Phone:', lang))}</strong> <a href="tel:{e(holding['phone_href'])}" dir="ltr">{e(holding['phone'])}</a></p>
      <p><strong>{e(_t('البريد الإلكتروني:', 'Email:', lang))}</strong> <a href="mailto:{e(holding['email'])}" dir="ltr">{e(holding['email'])}</a></p>
      <div class="page-hero-actions">
        <a class="btn btn-primary" href="https://wa.me/{e(str(holding['whatsapp']))}" rel="noopener noreferrer" target="_blank">{e(_t('تواصل عبر واتساب', 'Contact via WhatsApp', lang))}</a>
      </div>
    </div>
  </div>
</section>"""


def _careers_body(lang: str) -> str:
    """The approved careers page: intro + single CV form, no vacancies list."""
    text = C.PAGE_TEXT["careers"]
    return f"""
<section class="page-hero page-hero-intro">
  <div class="container narrow">
    <h1>{e(text['title'][lang])}</h1>
    <p class="section-lead">{e(text['intro'][lang])}</p>
    <p>{e(text['submit'][lang])}</p>
  </div>
</section>
{_form_section(lang, "careers", "gulf", None, heading=_t('بيانات التقديم', 'Application details', lang))}"""


def _legal_sections(lang: str, sections: list[dict]) -> str:
    blocks = []
    for section in sections:
        paras = "".join(f"<p>{e(p)}</p>" for p in section["body"][lang])
        blocks.append(
            f'<section class="legal-block"><h2>{e(section["heading"][lang])}</h2>{paras}</section>'
        )
    return "".join(blocks)


def _legal_body(lang: str, *, title_ar: str, title_en: str, intro_ar: str,
                intro_en: str, sections: list[dict]) -> str:
    holding = C.HOLDING
    name = holding["name_ar"] if lang == "ar" else holding["name_en"]
    address = holding["address_ar"] if lang == "ar" else holding["address_en"]
    return f"""
<section class="page-hero page-hero-intro">
  <div class="container narrow">
    <h1>{e(_t(title_ar, title_en, lang))}</h1>
    <p class="section-lead">{e(_t(intro_ar, intro_en, lang))}</p>
  </div>
</section>
<section class="section legal-copy">
  <div class="container narrow">
    {_legal_sections(lang, sections)}
    <p class="contact-legal">{e(name)}<br>{e(address)}<br>
      <a href="mailto:{e(holding['email'])}" dir="ltr">{e(holding['email'])}</a></p>
  </div>
</section>"""


def _privacy_body(lang: str) -> str:
    return _legal_body(
        lang,
        title_ar="سياسة الخصوصية",
        title_en="Privacy Policy",
        intro_ar="توضح هذه السياسة كيفية تعامل شركة ستارت أب سفير القابضة ذ.م.م مع البيانات الشخصية المقدمة عبر الموقع.",
        intro_en="This policy explains how START UPSPHERE HOLDING CO W.L.L handles personal data submitted through this website.",
        sections=C.PRIVACY_SECTIONS,
    )


def _terms_body(lang: str) -> str:
    return _legal_body(
        lang,
        title_ar="الشروط والأحكام",
        title_en="Terms and Conditions",
        intro_ar="شروط استخدام موقع شركة ستارت أب سفير القابضة، وطلبات الخدمات والتوظيف، وعرض المشاريع.",
        intro_en="The terms of use for the START UPSPHERE HOLDING website, covering service and career requests and the listing of businesses.",
        sections=C.TERMS_SECTIONS,
    )


def maintenance_page(lang: str, message: str | None = None) -> str:
    """A standalone maintenance notice (HTTP 503) for the public site.

    Minimal on purpose: no nav, no CMS context, so it renders even when the
    database is the very thing being maintained. Only the message is dynamic
    and it is escaped.
    """
    direction = "rtl" if lang == "ar" else "ltr"
    title = _t("الموقع تحت الصيانة", "Site under maintenance", lang)
    body = message or _t(
        "نعمل حاليًا على تحديث الموقع. يرجى المحاولة مرة أخرى بعد قليل.",
        "We are currently updating the site. Please try again shortly.",
        lang,
    )
    return f"""<!doctype html>
<html lang="{e(lang)}" dir="{e(direction)}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{e(title)} — {e(_brand(lang))}</title>
<link rel="stylesheet" href="/website/assets/styles.css">
</head>
<body class="site lang-{e(lang)}">
<main id="main" tabindex="-1">
<section class="page-hero">
  <div class="container center">
    <h1>{e(title)}</h1>
    <p>{e(body)}</p>
  </div>
</section>
</main>
</body>
</html>"""


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
def _cms_page_block(lang: str, page_ctx: dict | None) -> str:
    """Extra published content for a route, rendered *after* the V2 body.

    Additive by construction: with no published CMS page for the route this
    returns an empty string and the built-in V2 content is the whole page.
    Structured sections are escaped, never emitted as raw HTML.
    """
    if not page_ctx:
        return ""
    heading = (page_ctx.get("title") or {}).get(lang)
    body = (page_ctx.get("content") or {}).get(lang)
    parts = []
    if heading:
        parts.append(f'<h2 class="section-title">{e(heading)}</h2>')
    if body:
        parts.append(f'<div class="prose"><p>{e(body)}</p></div>')
    for section in page_ctx.get("sections", []):
        sec_heading = (section.get("heading") or {}).get(lang)
        sec_body = (section.get("body") or {}).get(lang)
        if sec_heading:
            parts.append(f'<h3 class="section-title">{e(sec_heading)}</h3>')
        if sec_body:
            parts.append(f'<div class="prose"><p>{e(sec_body)}</p></div>')
    if not parts:
        return ""
    return (
        '<section class="section cms-section"><div class="container">'
        + "".join(parts)
        + "</div></section>"
    )


def _cms_slides_section(lang: str, slides: list) -> str:
    """A CMS-managed hero carousel, rendered only when slides are published.

    Additive: with no active slides this returns "" and the built-in hero is
    unchanged. Slide copy and URLs are escaped; the image is constrained by CSS
    so any uploaded aspect ratio is safe.
    """
    if not slides:
        return ""
    items = []
    for slide in slides:
        title = (slide.get("title") or {}).get(lang)
        desc = (slide.get("description") or {}).get(lang)
        image = slide.get("image_url")
        cta_label = (slide.get("cta_label") or {}).get(lang)
        cta_url = slide.get("cta_url")
        media = (
            f'<img src="{e(image)}" alt="{e(title or "")}" loading="lazy">'
            if image
            else ""
        )
        actions = ""
        if cta_label and cta_url:
            actions = f'<a class="btn btn-primary" href="{e(cta_url)}">{e(cta_label)}</a>'
        items.append(
            f'<article class="cms-slide">{media}'
            f'<div class="cms-slide-body">'
            + (f'<h3>{e(title)}</h3>' if title else "")
            + (f'<p>{e(desc)}</p>' if desc else "")
            + actions
            + "</div></article>"
        )
    return (
        '<section class="section cms-slides"><div class="container">'
        f'<div class="cms-slide-track">{"".join(items)}</div>'
        "</div></section>"
    )


def _body_for(meta: PageMeta, cms=None) -> str:
    route = meta.route
    lang = meta.lang
    cms_companies = None
    if cms is not None and cms.companies:
        cms_companies = cms.companies
    if route == "home":
        body = _home_body(lang, cms_companies)
        if cms is not None and cms.slides:
            body = _cms_slides_section(lang, cms.slides) + body
    elif route.startswith("market-service:"):
        _, market, slug = route.split(":", 2)
        body = _market_service_body(lang, market, slug)
    elif route == "services":
        body = _services_body(lang)
    elif route == "opportunities":
        body = _opportunities_body(lang)
    elif route == "list-your-business":
        body = _list_body(lang)
    elif route == "group":
        body = _group_body(lang, cms_companies)
    elif route == "about":
        body = _about_body(lang)
    elif route == "careers":
        body = _careers_body(lang)
    elif route == "terms":
        body = _terms_body(lang)
    elif route == "privacy":
        body = _privacy_body(lang)
    elif route == "contact":
        body = _contact_body(lang)
    else:
        body = not_found_body(lang)
    if cms is not None and cms.pages:
        body += _cms_page_block(lang, cms.pages.get(route))
    return body


def render(meta: PageMeta, branding: dict | None = None, cms=None) -> str:
    """Render a full page for a resolved route."""
    return render_page(meta, _body_for(meta, cms), branding, cms)


__all__ = ["render", "render_page", "maintenance_page", "not_found_body", "e"]
