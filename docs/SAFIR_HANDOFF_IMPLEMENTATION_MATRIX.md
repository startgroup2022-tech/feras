# SAFIR Holding — Handoff Implementation Matrix

Source package: `Startup_Safeer_Developer_Handoff_v1.zip`
(`SPECIFICATION.md`, `content/*`, `previews/*`, `assets/*`), reviewed 2026-10-09.

This matrix tracks every requirement from the handoff against the existing
implementation. It is updated as work lands, not written once. Statuses:
COMPLETE · PARTIAL · MISSING · BLOCKED · VERIFIED.

## Authority and conflict

The handoff's own authority order (README §"ترتيب المرجعية") puts the
owner's newest decision first, then the approved Arabic copy and specification, then the
previews for *shape only*. The handoff explicitly says: *"If the handoff conflicts with
existing production functionality, preserve existing functionality and document the
conflict before implementing any change."*

**There is a real conflict.** The repository already carries an approved and deployed
public website (Phase 10, "V2 visitor journey") that is a *different concept* from this
handoff:

| | Deployed V2 site (present) | Handoff v1 (requested) |
|---|---|---|
| Frame | "Business & investment gateway", Bahrain + Saudi markets | Holding-company site |
| Navigation | Home · Opportunities · Business Services · Group Companies · About · Contact | Home · About · Group Companies · Business Opportunities · Careers · Contact |
| Service model | 4 services × 2 markets, each an indexable page with its own copy (`SERVICE_MARKET_CONTENT`) | 6 service options inside one "How can we help?" form |
| Group companies | 3 curated, `verified=false` trust entries | 9 canonical companies with full bilingual copy + contact |
| Markets | Bahrain, Saudi only | 6 Gulf opportunity countries |
| Tests | ~520 passing tests pin the V2 content model and routes | — |

Replacing the deployed site wholesale would delete a shipped, tested feature and break
hundreds of tests — a regression the handoff is at pains to avoid. Therefore this work
implements the parts of the handoff that are **faithful and non-conflicting**, and marks
the rest MISSING/BLOCKED rather than silently overwriting production. The public
website's operational behaviour and the internal platform are untouched.

## Implemented in this change (VERIFIED)

Canonical group-company dataset + interactive experience (handoff §3 "الشركات" and
§7 "الشركات: keyboard-accessible selector/accordion").

- Dataset extracted verbatim from `content/companies.json` into
  `backend/website/group_companies.py` (9 companies, approved order 1–9, bilingual
  copy, `null` preserved as "not provided").
- Desktop: selectable name list beside the selected company's detail; first company
  selected by default (`aria-expanded`, `aria-controls`).
- Mobile ≤600px: accordion — the chosen name opens its detail beneath it and the
  previous one closes; all nine names always visible, no horizontal scroll, no filters.
- Only supplied facts rendered: a `null` phone/email/whatsapp/website emits no link;
  the one company without an official English name shows its Arabic legal name
  (no translation is invented).
- Correct RTL/LTR via logical CSS properties; keyboard focus visible.
- Rendered on both the homepage (`#companies`) and `/group-companies`
  (+ Arabic `/ar/شركات-المجموعة`) and `/`.
- Tests: `tests/test_website_pages.py` (6 new cases), full suite green.

## Requirements matrix

| ID | Source | Requirement | Existing | Status | Verification |
|----|--------|-------------|----------|--------|--------------|
| GC-1 | §3 الشركات, §7 | 9 canonical companies, approved order | 3 placeholders | COMPLETE | `test_group_companies_dataset_matches_the_handoff` |
| GC-2 | §3, §7 | Desktop: list + selected detail, first open | grid of cards | COMPLETE | browser CDP 1440 (EN+AR) |
| GC-3 | §3, §7 | Mobile accordion, all 9 visible, no h-scroll | none | COMPLETE | CDP 390/600, `test_mobile_group_accordion_css_is_present` |
| GC-4 | §3 | Bilingual name/card/about/services | 3 EN/AR | COMPLETE | `test_group_companies_render_in_both_languages` |
| GC-5 | §3, §9 | `null` fields never shown/faked | n/a | COMPLETE | `test_group_company_actions_only_render_when_a_value_exists` |
| GC-6 | §7 | RTL/LTR, keyboard, visible focus | n/a | COMPLETE | CDP dir/lang, focus-visible CSS |
| HOME-1 | §3 الرئيسية | Hero → About → Group Companies → Opportunities → Help → Footer order | different order/concept | BLOCKED | conflict: V2 home is the deployed, tested concept |
| NAV-1 | §2 | Nav: Home·About·Group·Opportunities·Careers·Contact (+lang) | Home·Opp·Services·Group·About·Contact | BLOCKED | conflict: nav is pinned by V2 tests; careers route missing |
| OPP-1 | §3 الفرص | Latest 3 published opportunities, newest-first | `/api/v1/public/opportunities` list exists; no "latest 3" homepage block or detail page | MISSING | conflicts with V2 `/opportunities` market pages |
| OPP-2 | §3 | Country + sector filters, detail page, share | market/type filter only | MISSING | — |
| OPP-3 | §3 | Sold→`unavailable` keeps URL | not modelled | MISSING | — |
| SVC-1 | §4 | 6 service options, 7 countries | 4 services × 2 markets | MISSING | conflicts with `SERVICE_MARKET_CONTENT` and its tests |
| CAREER-1 | §3/§4 | Careers page + CV upload flow | none | MISSING | new model, storage, admin view required |
| PROJ-1 | §4 | Submit-a-project flow + proof doc | closest: `business-listing` lead | MISSING | — |
| LEGAL-1 | §3 | Approved privacy + terms pages | privacy/terms not published | MISSING | blocked: handoff says privacy incomplete for launch |
| SEO-1 | §8 | Per-page metadata, canonical, hreflang, sitemap, OG | implemented for V2 routes | PARTIAL | applies to V2; new routes would need the same |
| A11Y-1 | §7/§10 | Keyboard, focus, labels, contrast, reduced-motion | present | COMPLETE | suite + previews |
| SEC-1 | §6 | Allow-list uploads, size caps, private storage, rate limit | implemented (`core/storage.py`, public limiter) | COMPLETE | `test_website_leads.py` |
| PLAT-1 | §5/§9 | Internal platform intact (auth, RBAC, tabs, header) | unchanged | COMPLETE | full suite incl. header regression |

## Blocked / open items (do not implement blind)

- **Concept conflict** (HOME-1, NAV-1, SVC-1, OPP-*): a decision is required from the
  owner — keep the deployed V2 gateway and layer the handoff's group/company content on
  top (this change), or retire V2 in favour of the handoff (a large, test-breaking
  rewrite that must be a deliberate, separate project).
- **Missing production facts** the handoff itself lists as `null`/pending: high-res logo,
  company logos, hero image licence, real opportunities, careers recipient mailbox,
  upload limits, net-profit rule. None may be invented.
- **Privacy incomplete for launch**: `content/PRIVACY-AR.md` carries an internal note that
  retention, hosting, processors and legal basis are undecided.
