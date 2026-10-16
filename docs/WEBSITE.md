# Safir Holding 2027 — Public Website Operations

The public website is a separate experience from the internal platform. It is
server-rendered, Arabic-first and RTL, bilingual (AR/EN) and built to be indexed
by search engines. This document covers what it is, how it is deployed and how
to operate it.

## 1. What it is (and is not)

It **is**:

- A public gateway around two markets — Bahrain and Saudi Arabia — and a small
  set of visitor needs (opportunities, company formation, feasibility studies,
  investment interest, listing a business, general contact).
- Server-rendered HTML: every route is a real document with its own title,
  description, canonical URL and hreflang pair.
- The front door that feeds qualified requests into the internal platform.

It is **not**:

- A rebuild of the internal platform. The Dynamic Forms Builder, Requirements
  Engine, Workflow Builder, Approval Engine, Document Management, Dashboard,
  Companies and Monthly Reporting modules are untouched and remain the system of
  record.
- A place for confidential data. Published opportunities are a deliberately
  narrow shape; a listing is never public until the Holding reviews it and
  writes the public-facing copy.

## 2. Layout: one origin, two experiences

| Path            | Served by         | Indexable |
| --------------- | ----------------- | --------- |
| `/`, `/ar`, `/<market>/<service>`, ... | public website (`website/`) | yes |
| `/sitemap.xml`, `/robots.txt` | public website | n/a |
| `/website/assets/*` | public website static files | assets |
| `/platform`     | internal platform (`frontend/`) | **no** (`X-Robots-Tag: noindex`) |
| `/api/v1/*`     | JSON API | **no** |

Two settings control this:

- `SPLIT_PUBLIC_SITE` — `true` in staging/production: the website owns the root
  and the platform moves under `PLATFORM_PATH`. `false` in development: the
  platform keeps the root so local workflows are unchanged.
- `PLATFORM_PATH` — default `/platform`.
- `WEBSITE_BASE_URL` — absolute origin used in canonical tags, hreflang
  alternates and the sitemap. Leave blank in development (relative URLs are
  emitted); set it in staging/production.

## 3. Routes

Top-level pages (English / Arabic):

| Page | English | Arabic |
| ---- | ------- | ------ |
| Home | `/` | `/ar` |
| Opportunities & projects | `/opportunities` | `/ar/الفرص-والمشاريع` |
| Business services | `/services` | `/ar/خدمات-الأعمال` |
| Group companies | `/group-companies` | `/ar/شركات-المجموعة` |
| About | `/about` | `/ar/عن-القابضة` |
| Contact | `/contact` | `/ar/تواصل` |
| List your business | `/list-your-business` | `/ar/اعرض-شركتك` |

Market/service pages, one per market × service, in both languages:

- English: `/<market>/<service>` e.g. `/bahrain/company-formation`
- Arabic: `/ar/<market-ar>/<service-ar>` e.g. `/ar/البحرين/تأسيس-شركة`

The market and service sets live in `backend/website/content.py`; the route
table and page metadata in `backend/website/pages.py`. Adding a service or a
market there automatically extends the pages, the sitemap and the hreflang
pairs — they cannot drift apart.

## 4. Public API

All endpoints are unauthenticated and live under `/api/v1/public`. They accept
no actor, role or company id, and return no internal record.

| Method | Path | Purpose |
| ------ | ---- | ------- |
| POST | `/api/v1/public/leads/company-formation` | Company formation request |
| POST | `/api/v1/public/leads/feasibility` | Feasibility study request |
| POST | `/api/v1/public/leads/opportunity-interest` | Interest in a published listing |
| POST | `/api/v1/public/leads/business-listing` | List a business (multipart, optional attachments) |
| POST | `/api/v1/public/leads/contact` | General contact |
| GET  | `/api/v1/public/opportunities` | Published listings (narrow public shape) |

A successful submission returns only a reference and a timestamp, e.g.
`{"reference": "SAF-CF-7F3A91", "received_at": "..."}`.

### Abuse controls

- **Rate limit** — per client IP, sliding window (`PUBLIC_RATE_LIMIT` per
  `PUBLIC_RATE_WINDOW_SECONDS`). Separate from the login limiter.
- **Honeypot** — a hidden `honeypot` field. When filled, the request receives a
  normal success response but nothing is stored, so a bot learns nothing.
- **Validation** — every field has an explicit maximum length and closed-set
  enums; cross-field rules (e.g. Saudi requires a target city) are enforced
  server-side.
- **Attachments** — capped by count (`PUBLIC_MAX_ATTACHMENTS`), type and size
  through the same storage validation as internal documents.

### Market and service routing

A submission is classified and routed **server-side** from the page context, not
from a free-text field. The rule table is `ROUTING_TABLE` in
`backend/services/website_lead_service.py`, e.g.:

- `company_formation` + `bahrain` → `formation_bahrain`
- `feasibility_study` + `saudi` → `feasibility_saudi`
- `business_listing` / `investment` / `opportunity_interest` → `investment_desk`
- `general_contact` → `holding_front_desk`

On creation the responsible role is notified through the existing notification
centre, and the existing webhook integration fires `lead.created` (and
`lead.status_changed` on updates).

## 5. Internal handling

Authenticated users with the right permissions manage leads under
`/api/v1/leads`:

| Permission | Grants |
| ---------- | ------ |
| `website_lead.read` | View leads, attachments, stats |
| `website_lead.manage` | Edit, assign and re-route a lead |
| `website_lead.status_change` | Move a lead through its pipeline |
| `website_opportunity.review` | Approve/reject a submitted listing |
| `website_opportunity.publish` | Publish a listing publicly |

Default role grants: **Holding Owner / Admin** have the full set;
**Business Development** owns the pipeline; **Marketing** can read and move
leads; **Holding Finance** can read. Company-level roles have no access.

The internal UI exposes a **Website Leads** view (`/platform/#leads`) with funnel
stats, a filterable list, lead detail and (for managers) status/priority updates.

## 6. Publishing an opportunity

A listing submitted publicly is created with `is_public = false` and status
`submitted`. To make it public:

1. Review the submission in the platform.
2. Write the public-facing copy (title and optional summary, AR and/or EN).
3. Call the review endpoint with `status: "published"` and `publish: true`.

Publishing without public copy is refused (422) — the confidential description
is never echoed as the public text. The public list returns only the fields the
Holding has cleared for publication.

## 7. SEO

- `robots.txt` allows the public site and disallows `/api/` and `PLATFORM_PATH`.
- `sitemap.xml` lists every page in both languages with inline hreflang
  alternates.
- Every page carries canonical, hreflang (`en`, `ar`, `x-default`), Open Graph
  and Twitter tags.
- Structured data is limited to an `Organization` node (name and URL only — no
  invented address, phone, founding date or rating) and `BreadcrumbList`.
- The platform and the API are served with `X-Robots-Tag: noindex, nofollow`.

## 8. Content rules

Nothing on the site is fabricated. There are no invented statistics,
transaction values, client counts, approvals, awards, partnerships, founding
years or locations. Group companies are shown for trust only and each entry
carries a `verified` flag for the internal review that will confirm it; the
Saudi entities are not listed until their legal structure is confirmed.

## 9. Data residency

The platform and the website run on the same infrastructure and the same
database. Lead data (contact details, request details, attachments, attribution)
stays within that environment. There is no third-party analytics, tag manager or
CDN in the request path; the only external requests a visitor's browser makes are
to Google Fonts. If the Holding requires fonts to be self-hosted for residency or
offline operation, download the two families and replace the `<link>` tags in
`backend/website/renderer.py`.

## 10. Deployment

Follow `docs/DEPLOYMENT.md` for the host, service and proxy. Website-specific
points:

1. Set in the environment file:
   ```
   SPLIT_PUBLIC_SITE=true
   PLATFORM_PATH=/platform
   WEBSITE_BASE_URL=https://<host>
   PUBLIC_RATE_LIMIT=20
   PUBLIC_RATE_WINDOW_SECONDS=600
   PUBLIC_MAX_ATTACHMENTS=5
   ```
2. Apply the Phase 10 migration before starting the new version:
   ```
   python -m alembic upgrade head
   ```
   It creates `website_leads`, `website_lead_attachments` and
   `website_opportunities`; it does not touch any existing table.
3. Nginx serves the app under `/`; the platform is under `/platform` and
   `/website/assets/` is long-cached (see `deploy/nginx/safir-staging.conf`).
4. Verify after deploy:
   - `GET /` returns the Arabic home page (RTL) with a 200.
   - `GET /ar` returns the Arabic home page; `GET /bahrain/company-formation`
     returns the English market page.
   - `GET /robots.txt` disallows `/api/` and `/platform`.
   - `GET /sitemap.xml` is well-formed and lists every page twice.
   - `GET /platform/` returns the internal app with `X-Robots-Tag: noindex`.
   - Submitting the contact form returns a reference and creates a lead visible
     in the platform's Website Leads view.

## 11. Tests

```
python -m pytest tests/test_website_leads.py tests/test_website_pages.py -q
```

`test_website_leads.py` covers the public API, routing, attribution, honeypot,
consent, opportunity privacy and internal permissions.
`test_website_pages.py` covers route resolution, per-page metadata, hreflang,
sitemap/robots consistency, RTL/LTR, escaping and indexability.
