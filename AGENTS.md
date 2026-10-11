# AGENTS.md — Safir Holding 2027

Arabic-first, RTL executive Holding Management & BI platform. **Not an ERP** —
no HR, inventory, payroll, procurement, project management, contracts, meetings,
OKR, or approval-matrix modules.

Two halves in one repo:

- `frontend/` — the approved 1920×1080 UI prototype (`index.html`, `styles.css`, preview PNGs).
- `backend/` — the Phase 1 FastAPI service that turns the prototype into real software.

## Commands

```bash
# Install
pip install -r requirements.txt -r requirements-dev.txt

# Migrate + seed a local database
APP_ENV=development DATABASE_URL="sqlite:///./safir_dev.db" python -m alembic upgrade head
APP_ENV=development DATABASE_URL="sqlite:///./safir_dev.db" python scripts/seed_demo.py

# Run
APP_ENV=development DATABASE_URL="sqlite:///./safir_dev.db" python -m uvicorn backend.main:app --reload

# Tests (config in pytest.ini; tests are self-contained and create their own DB)
python -m pytest tests/ -q

# Schema drift check — must say "No new upgrade operations detected."
APP_ENV=development DATABASE_URL="sqlite:///./safir_dev.db" python -m alembic check
```

`alembic.ini` deliberately does not hardcode `sqlalchemy.url`; `alembic/env.py`
reads `DATABASE_URL` from the environment. Always pass it explicitly.

## Architecture

Request flow: `api/v1/*` (thin routers) → `services/*` (all business rules) →
`repositories/scoped.py` (row-level scoping) → `db/models/*` (SQLAlchemy).

- `core/config.py` — `settings` (pydantic-settings, env-driven).
- `rbac/permissions.py` — `Perm` constants; `rbac/authorization.py` — `require_permission`,
  `require_company_access`, `has_permission`, `is_holding_wide`.
- `services/dashboard_service.py` — every KPI computed live; nothing hardcoded.
  Group financial totals only count **approved, financially verified** figures.
  `_attention_rows` / `attention_payload` surface companies needing follow-up.
- `services/ai_service.py` — `NullProvider` (deterministic, Arabic) until Phase 2.
  Context is assembled **after** scope checks, so the provider cannot leak other
  companies' data. Answers must only restate figures present in the context.
- `services/audit_service.py` — every mutating action and AI call writes an `AuditLog`.

## Conventions

- **Layering is strict**: routers do not contain business logic; services do not
  build responses; repositories own scoping queries.
- **Isolation**: "not yours" and "does not exist" both return 404. Never reveal
  that an out-of-scope record exists.
- **Pydantic v2 gotcha**: `field_validator` does **not** run on fields left at
  their default, so cross-field rules (e.g. `flagged_reason` required when
  `is_financially_accurate=False`) must use `model_validator(mode="after")`.
  See `tests/test_schemas.py`.
- **SQLAlchemy gotcha**: do not add a single-column `Index(...)` that duplicates
  `index=True` on the same column — the duplicate name breaks `create_all`.
- **Arabic-first**: user-facing strings, seeded data, and AI output are Arabic.
  `full_name_ar` is required; `full_name_en` is optional.
- Money is `Decimal`/`Numeric(18, 2)`; losses are negative and allowed.

## Testing

`tests/conftest.py` provides `db`, `client`, `auth`, `make_user`, `make_company`,
`make_report`, `make_request`, and the shared `world` fixture (two companies with
reports, users per role, support requests). Each test module owns its own
scenario; do not widen `world` for a single test — build the extra rows locally.

Suites: `test_auth`, `test_isolation`, `test_rbac`, `test_reports`, `test_support`,
`test_dashboard`, `test_ai`, `test_admin`, `test_schemas`, `test_ai_providers`,
`test_insights`.

## Known gaps

Add these in a later phase rather than papering over them in tests:

- `AI_PROVIDER` supports `none` (deterministic, default), `openai`/`azure` and
  `local`; the hosted providers are implemented but unverified against a live
  endpoint.
- Frontend is still the approved static dashboard plus `frontend/app.js`, which
  hydrates it from the real APIs when served by the backend. There is no login
  screen or write flows in the browser yet.

## Phase 2 additions

Built on top of the Phase 1 foundation (do not rebuild Phase 1):

- `backend/ai/` — provider abstraction (`get_provider`), deterministic
  `NullProvider`, OpenAI-compatible/local providers, and number *grounding*
  (`find_ungrounded`) so an answer can never cite a figure absent from context.
- `backend/services/insights_service.py` — four data-driven executive insights
  (revenue change, attention, opportunity, financial review), exposed at
  `GET /api/v1/ai/insights`.
- `backend/services/admin_service.py` — user list/update and company-access
  grant/revoke; `PATCH /users/{id}`, `PATCH /companies/{id}`.
- `backend/core/storage.py` — attachment storage with content-type allow-list,
  size cap and path-traversal guard; wired into `POST/DELETE
  /monthly-reports/{id}/attachments`.
- Dashboard now returns `change_vs_previous` and `companies_performance`
  (per-company revenue/expenses/net, growth vs. previous month, report status).
- `PATCH /support-requests/{id}/assign` (owner-only).

## Frontend: real app (auth-gated, live data)

The dashboard is now the working application, not a mockup. `frontend/app.js`
loads every figure from the API for the signed-in user and has no demo
fallback — while a request is in flight the section shows a loading state, and
a failure shows an explicit error/empty state.

- `frontend/auth.js` (`window.SafirApi`) owns the JWT session: login, logout,
  transparent single refresh on 401, and `get/post/patch`. Tokens live in
  `localStorage` under `safir.session.v1`; they are never put in the URL or
  HTML. `setBase()` exists but the app runs same-origin (empty base).
- Login gate: `.login-screen` (fixed, z-index 1000) covers the app until the
  backend authenticates the user; `.stage-wrap` is hidden via
  `body:not(.authed)`. `#loginForm`, `#loginEmail`, `#loginPassword`,
  `#loginBtn`, `#loginError`, `#logoutBtn` are the hooks.
- Reporting period: the backend defaults to the *current* calendar month, which
  has no data in a seeded environment. Unless `?year=&month=` is pinned,
  `app.js` derives the latest month that actually has data from
  `/api/v1/monthly-reports` and uses it for the dashboard, insights and AI.
- RBAC mirroring: sections carry `data-perm="<perm> <perm>"` (any-of). After
  `/auth/me`, `applyPermissions()` adds `.perm-hidden` to sections the user
  cannot access, and the loader only calls permitted endpoints. Company users
  get `/dashboard/company/{id}` and `/ai/company`; holding users get
  `/dashboard/holding` and `/ai/holding`.
- `/auth.js` is served by an explicit route in `backend/main.py`.

Still true: anything a live API returns is HTML-escaped before insertion (the
AI answer included), since a real LLM provider could otherwise emit markup.

## Frontend polish (executive dashboard, v1)

- Dashboard cards need the report list even when `?year=&month=` is pinned, so
  `enterApp()` preloads `ensureReports()` + `ensureCompanies()` before the
  dashboard, support and insight fetches. Without this the cards fall back to
  "Follow up" instead of "View Report" for companies that did submit.
- All percentage deltas render as bilingual `<span class="ar">…٪</span><span
  class="en">…%</span>` via `growthHtml()` / `hydrateKpis()`, so the AR/EN
  toggle never shows a stray Arabic `٪` in English mode.
- `errText(err)` maps HTTP status to a short bilingual sentence and never
  surfaces a raw object or `[object Object]`; login uses the same helper.
- `openModal(opts)` passes `(root, body)` to `onMount`; use `body` instead of
  re-querying `#modalBody`. Assignment uses the real user directory from
  `/api/v1/users` (no free-typed ids).
- `createReportForm()` validates year (2000–2100), month (1–12) and requires at
  least one of revenue/expenses before POSTing.
- Responsive: the `.stage` fills the viewport on desktop
  (`height:calc(100vh - 28px)`, `max-width:1920px`) so the live app reads as an
  application, not a fixed design board. Only `?export=1` renders the
  historical 1920×1080 canvas at 1:1. At ≤1180px the stage reflows
  (board becomes one column, `.app-view` becomes in-document instead of an
  absolute overlay) so nothing clips. Overflow guards (`min-width:0`) on
  dynamic text cells, and the support table drops its department column at
  ≤560px.

## Frontend: group administration view (Phase 2)

- The `admin` nav item (`.nav-item[data-view="admin"]`, section
  `#view-admin`) is gated on `company.read ownership.read department.read
  user.read_all role.read` and backed by `frontend/app.js renderAdmin()`. It
  is a tabbed surface, not a dashboard card set.
- Tabs are declared in `ADMIN_TABS` / `ADMIN_TAB_PERM`; only tabs the caller
  can read are shown, and `firstTab()` picks the landing tab. Each tab loads
  lazily on first open.
- The admin view uses one delegated `click` handler (`onAdminClick`) and one
  delegated `submit` handler (`onAdminSubmit`) bound to `#adminContent` once
  (`STATE.adminBound`), so re-rendering panels never rebinds listeners.
- Every admin control is permission-scoped: `group.manage`, `ownership.manage`,
  `company.manage`, `department.manage`, `user.manage`, `permission.assign`
  gate the forms/buttons; reads are ungated within an already-visible tab.
- Admin list endpoints return `{ items, total }` (`PageOut`); users and audit
  trail paginate via `STATE.adminUsers` / `STATE.adminAudit` offsets.
- `auth.js` also exposes `put` (used for role-permission updates).
- Do not expose an "Administration" nav item to company-scoped users — the
  nav-perm check plus the backend 403s keep it holding-only by design.

## Phase 3: dynamic operations (forms, requirements, workflows, approvals, documents)

Migration `34f510488f9c` (down_revision `1b786167cd02`) adds five cooperating
capabilities. Each follows the same shape: models in `db/models/*`, rules in
`services/*`, thin routers in `api/v1/*`, schemas in `schemas/ops.py`, and a
matching `tests/test_*.py`.

- **Dynamic Forms Builder** — `form_service` owns forms, versions and fields.
  A form is a definition plus `FormVersion` rows; fields and requirements hang
  off a version. `publish_form` freezes the latest version as
  `published_version`; a new field invalidates the published version until it
  is republished. `FormOut.field_count` counts the latest version's fields —
  do not recompute it from `latest_version_number` (that is the version number,
  not a field count).
- **Requirements Management** — `requirement_service` adds per-form requirements
  (`document` / `field`), mandatory or optional.
- **Workflow Builder** — `workflow_service` owns `WorkflowDefinition` → ordered
  steps. Steps carry an `assignment_type` (`user`, `role`,
  `department_manager`, `company_manager`, `submitter_manager`) resolved to a
  concrete assignee at submit time. `_assert_can_configure_form` reuses the form
  service's scope check, so a workflow can never be built for a form the actor
  cannot configure.
- **Submission + Approval Engine** — `submission_service.create_submission` /
  `submit_submission`. Submitting a definition whose form is published starts a
  `WorkflowInstance` and its first `ApprovalTask`. A submission whose mandatory
  requirements are unmet is recorded as `incomplete` and submission raises
  `ConflictError` (the record still exists, by design — it drives the
  "needs attention" queue). `approval_service.act` moves the task and advances
  the instance; the final approval marks the submission `approved`.
- **Document Management** — `document_service` + `core/document_storage.py`
  store files with a content-type allow-list and size cap. `seed_default_categories`
  populates a fixed category list; documents can carry an expiry date and can be
  attached to a submission to satisfy a `document` requirement.
- **RBAC** — baseline operator read covers `FORM_READ`, `REQUIREMENT_READ`,
  `WORKFLOW_READ`, `SUBMISSION_READ_OWN`, `APPROVAL_READ_OWN`, `APPROVAL_ACT`,
  `DOCUMENT_READ`, `DOCUMENT_UPLOAD`.

Frontend surfaces: `requests` (`renderRequestsView`), `approvals`
(`renderApprovalsView`, personal queue), `documents` (`renderDocumentsView`),
and two admin tabs, `builder` and `workflows`. `/api/v1/approvals/my` is
per-user: an owner sees an empty queue because no task is assigned to them.

### Demo operations data

`scripts/seed_demo.py` seeds the Phase-3 demo through the services (never raw
inserts) so the data matches what the app can actually do:

- one holding-wide published form `capex_request` (3 fields + a mandatory
  document requirement) and one two-step workflow `capex_flow`;
- three submissions: `CAPEX_RE-000001` approved end-to-end, `CAPEX_RE-000002`
  incomplete (missing quotation), `CAPEX_RE-000003` awaiting finance review in
  the accountant's queue;
- two documents, one expiring soon.

`_seed_operations` is idempotent (skips if `capex_request` exists). `_reset`
purges options rows explicitly because forms/submissions/documents are
holding-scoped and not company-cascaded, so deleting companies alone would
leave them orphaned. Re-run with `--reset` after changing the operations seed.
Demo accounts use password `SafirDemo!2027`.

## Phase 6-9 — notifications, analytics, integrations

- **Notification centre** (`notification_service`, `api/v1/notifications.py`) —
  the inbox is always the caller's own (filtered by `recipient_id`, never a
  query param). `POST /notifications/scan-expiring` is idempotent and gated by
  `notification.manage`. Emitting an event that has no recipients is a no-op.
- **Advanced analytics** (`analytics_service`, `api/v1/analytics.py`) — four
  families (holding / operations / compliance / investment), each behind its
  own permission so operational analytics can be granted without exposing group
  financials. Every figure is computed inside the caller's company scope; query
  params only ever narrow, never widen, that scope.
- **Executive briefing** (`executive_intelligence_service`) — grounded and
  permission-shaped. The null provider returns a deterministic Arabic/English
  summary and never restates a figure that is not present in the context.
  `Source: none` means no LLM provider is configured, not that data is missing.
- **Integrations** (`integration_service`, `api/v1/integrations.py`) — webhook
  endpoints with one-time signing secrets (returned only on create/rotate, never
  from list/read) and a delivery log. Outbound URLs are validated for scheme,
  host resolution and private ranges; `UnsafeUrlError` subclasses
  `ValidationError` so it maps to 422. An unresolvable host is a 422, not a 500.
- **Migration head** is now `5ff680970d75` (phase 6-9: `notifications`,
  `webhook_endpoints`, `webhook_deliveries`). `tests/test_postgres.py` asserts
  the linear chain, so adding a revision means updating that test.
- **Existing dev DBs** need `bootstrap_rbac` re-run to pick up the new
  permissions before the phase 6-9 endpoints return 200 instead of 403.
- **Permission gating is two-layer**: nav/admin tabs and analytics sub-tabs are
  hidden client-side by permission, and the endpoints enforce the same checks.
  A `company_manager` sees only the executive briefing tab and no
  integrations/audit tabs; a `holding_owner` sees everything.

## Phase 10 — public website (separate experience)

The public website is a second, distinct experience in the same repo and origin,
**not** a redesign of the internal platform. Full operations doc: `docs/WEBSITE.md`.

- **Layout** — `SPLIT_PUBLIC_SITE` decides who owns the root. `true`
  (staging/production): website at `/`, platform under `PLATFORM_PATH`
  (`/platform`) with `X-Robots-Tag: noindex`. `false` (development): platform
  keeps the root so local workflows are unchanged. `WEBSITE_BASE_URL` feeds
  canonical/hreflang/sitemap absolute URLs.
- **Content model** — `backend/website/content.py` is the single source of
  truth (markets, services, nav, per-market copy, group companies). Pages,
  sitemap and hreflang are all derived from it, so they cannot drift.
  `backend/website/pages.py` resolves a path to `PageMeta`;
  `backend/website/renderer.py` renders the HTML; `backend/website/seo.py`
  builds meta tags, `robots.txt` and `sitemap.xml`. Arabic is the default and
  RTL; English is a separate URL with `dir="ltr"`.
- **Public API** — `/api/v1/public/leads/*` (formation, feasibility,
  opportunity-interest, business-listing, contact) and
  `/api/v1/public/opportunities`. All unauthenticated, closed-set validated,
  rate-limited per IP, honeypot-protected. A submission returns only a
  reference and a timestamp; the public opportunity shape is deliberately
  narrow (no description, no value range).
- **Lead service** — `website_lead_service.create_lead` classifies market and
  service server-side, applies `ROUTING_TABLE` (e.g. `company_formation` +
  `bahrain` → `formation_bahrain`), copies attribution verbatim, notifies the
  responsible role via `notification_service`, and emits `lead.created` via
  `integration_service`. Honeypot hits return a normal success but store
  nothing.
- **Listings** — a submitted listing is private (`is_public=false`,
  `status=submitted`). Publishing requires `website_opportunity.publish` **and**
  Holding-written public copy; the confidential description is never echoed.
- **Internal API/UI** — `/api/v1/leads` (list/detail/update/stats) gated by
  `website_lead.read` / `.manage` / `.status_change` and
  `website_opportunity.review` / `.publish`. The platform's `leads` view
  (`#view-leads`, `renderLeads()` in `frontend/app.js`) shows funnel stats, a
  filterable list and a detail modal.
- **Migration** — `9615c678609f` (down_revision `5ff680970d75`) adds
  `website_leads`, `website_lead_attachments`, `website_opportunities`. It does
  not alter existing tables. `tests/test_postgres.py` asserts the chain, so
  update it when adding a revision.
- **Existing dev DBs** need `bootstrap_rbac` re-run to pick up the new
  permissions before the lead endpoints return 200 instead of 403.
- **Tests** — `tests/test_website_leads.py` (public API, routing, attribution,
  honeypot, privacy, permissions) and `tests/test_website_pages.py` (routes,
  metadata, hreflang, sitemap/robots, RTL/LTR, escaping, indexability). The page
  tests use a `public_client` fixture that enables `SPLIT_PUBLIC_SITE`, i.e. the
  production layout.
- **Content rule** — never fabricate statistics, values, clients, awards,
  partnerships, years or locations. Group companies carry a `verified` flag;
  unverified entities stay out until confirmed.
- **Public design system** — `website/assets/styles.css` is the single visual
  layer for the public site (the internal platform has its own `styles.css`).
  Both directions are driven by logical properties (`inline-start`/`end`), so
  RTL and LTR share one sheet; `html[lang="en"]` only swaps the font stack and
  eyebrow tracking. The header is a three-part flex row (brand · centred nav ·
  actions) and collapses to a drawer at 1150px — the breakpoint sits just above
  the widest nav so the links can never collide with the brand or the language
  switch. The drawer is driven by `.header-menu.is-open`, toggled in
  `website/assets/app.js`, and the language switch stays in the header bar
  (only the links move). The language control is a two-option segmented switch
  (`.lang-switch` / `.lang-opt.is-on`) where each option links to the current
  page's mirror. Keep both options explicit rather than a single toggle link.
  The brand wordmark and subtitle are `white-space: nowrap` with ellipsis, so
  branding can never wrap into the navigation.

## Configurable website logo (branding)

- The public header logo is **not** hardcoded: it is uploaded from the admin
  panel (Administration → Structure & ownership → "Website branding (logo)")
  and rendered by the website. Until one is uploaded the header shows the
  built-in SVG fallback (`data-brand-fallback`); an uploaded logo renders as
  `data-brand-logo` inside `.brand-logo`, which is height-fixed with
  `object-fit: contain` so any aspect ratio/dimension fits without distortion.
- Storage: `backend/core/branding_storage.py` reuses the upload root and its
  path-traversal guard, with a **raster-only** allow-list (PNG/JPEG/WebP/GIF;
  SVG is deliberately excluded — it can carry script and renders on every
  page). Keys are fresh UUIDs + a server-derived extension, so a client
  filename never reaches the filesystem. 4 MiB cap.
- Model: four nullable columns on `Holding` (`logo_storage_key`,
  `logo_content_type`, `logo_original_name`, `logo_updated_at`). The binary is
  never in the DB; only the opaque key + display metadata are.
- Service/routes: `backend/services/branding_service.py`; admin
  `GET/POST/DELETE /api/v1/admin/branding[/logo]` gated on `group.manage` (no
  new permission) and audited (`branding.logo_updated` / `.logo_removed`).
  Public read-only `GET /api/v1/public/branding` (URL only, never the key) and
  `GET /api/v1/public/branding/logo` (streams the file, 404 when none).
  `logo_url` is **derived**, not stored, and carries a `?v=` cache-buster.
- Graceful degradation: if the Holding points at a key whose file has gone, the
  URL is suppressed and the site falls back to the built-in mark instead of a
  broken image; `main._public_branding()` also swallows any lookup failure so a
  database blip can never 500 a public marketing page.
- Migration `b7f1a7747880` (down_revision `9615c678609f`) adds the four
  columns. `tests/test_postgres.py` asserts the chain, so update it when adding
  a revision. Tests: `tests/test_branding.py` plus header cases in
  `tests/test_website_pages.py`.

## Final UX/i18n pass (pre-production)

- **Bilingual dynamic strings** — language switching toggles
  `html.lang-ar` / `html.lang-en` in CSS (`.ar` hidden unless `lang-en`, and
  vice-versa), so any markup emitted with `dual(ar, en)` flips without a
  re-render. `dual()` in `frontend/app.js` is the canonical helper.
- **Placeholders and tooltips** — a language switch must not require
  re-rendering. `phAttr(key)` emits `placeholder` + `data-ph-ar` /
  `data-ph-en`; header buttons use `title` + `data-title-ar` /
  `data-title-en`. `applyI18n(root)` re-applies both and is called from
  `setLang` alongside `refreshActiveView` (which no-ops when `USER` is null).
- **Values baked into server-driven markup** — `refreshActiveView()` re-runs
  the active renderer (`renderAdminTab(STATE.adminTab)` or `loadView(view)`)
  on language change so any string not emitted through `dual()` is rebuilt.
- **Permission metadata** — `backend/rbac/permission_metadata.py` is the
  single source for the permission catalogue (`describe()`, `catalogue()`,
  `unknown_codes()`, `category_order()`). The admin UI consumes
  `/api/v1/admin/permissions/catalogue`; both name/description fields are
  bilingual. `tests/test_permission_metadata.py` asserts every known code
  resolves and categories stay ordered.
- **Role metadata** — `ROLE_DEFINITIONS` in `backend/rbac/permissions.py`
  carries `name_ar`/`name_en` and `description`/`description_ar` for every
  role; `rbac_service.sync_roles()` seeds both descriptions into the `roles`
  table (`description` is the English text, `description_ar` the Arabic
  counterpart). `RoleOut`, `RoleCreateRequest`, `RoleUpdateRequest` and the
  `/api/v1/admin/roles` + `/api/v1/rbac/roles` payloads expose both, and the
  Roles & Permissions UI renders them with `dual()` so a language switch
  updates the role card without a reload. `tests/test_rbac.py` asserts every
  definition is bilingual and the endpoint returns both descriptions.
- **Platform header on phones** — the internal platform `.h-actions` cluster
  (language · search · notifications · messages · profile · sign-out) is wider
  than a phone viewport. A `@media (max-width:560px)` rule lets the cluster take
  the full row, and `@media (max-width:480px)` collapses the profile text
  (`.p-meta`) and the Sign out label (`.logout-btn span`) so nothing is pushed
  off-screen. Controls are never removed: Sign out keeps its icon and
  `data-title-*`/`title`, so it stays reachable in RTL and LTR. Regression:
  `tests/test_website_pages.py::test_platform_header_keeps_every_control_reachable_on_phones`.
- **Avatar initials** — department chips use `deptInitialHtml()` (Latin
  initials under `lang-en`, Arabic under `lang-ar`); company/user avatars keep
  the first letter of the Arabic name as a stable identity mark.

## Handoff v1 — group companies (interactive)

The approved `Startup_Safeer_Developer_Handoff_v1` package specifies a *holding-company*
site that **conflicts with the deployed V2 visitor-journey site** (different navigation,
service model, markets and group-company list). Per the handoff's own rule ("preserve
existing functionality and document the conflict"), only the non-conflicting, faithful
slice has been implemented; the full matrix and the conflict analysis live in
`docs/SAFIR_HANDOFF_IMPLEMENTATION_MATRIX.md`. Do not silently replace the V2 site.

- **Canonical dataset** — `backend/website/group_companies.py` holds the nine approved
  companies (order 1–9) extracted verbatim from the handoff's `content/companies.json`.
  It is the single source of truth; `ordered()` returns them in approved order. A
  `null` field means "not provided" and is never rendered as a value or a fake logo.
- **Component** — `_group_companies_section()` in `renderer.py` renders a selectable
  name list beside the selected company's detail (desktop) that becomes an accordion at
  `≤600px` (`website/assets/styles.css`, `.company-list` / `.company-choice` /
  `.inline-detail`). The first company is selected by default; all nine names stay
  visible with no horizontal scroll and no filters. Interaction is in
  `website/assets/app.js` (`[data-company-selector]`, `[data-company-choice]`,
  `[data-company-panel]`, `[data-company-detail]`).
- **Names** — `_localized_name()` falls back to the Arabic legal name when `name_en` is
  `null` (one company in the dataset); a translation is never invented. `null`
  phone/email/whatsapp/website emits no contact link.
- **Placement** — shown on `/` and `/group-companies` and their Arabic mirrors (`/ar`,
  `/ar/شركات-المجموعة`).
- **Tests** — `tests/test_website_pages.py` (dataset order, all-nine rendering, both
  languages, null-safety, mobile accordion CSS).

## Revision brief — listing attachments and careers CV (items 06, 14)

- **Two upload purposes, two rules** — a business listing may carry one internal
  *proof-of-relationship* document and up to `PUBLIC_MAX_LISTING_PHOTOS` (10)
  project *photos*. They are separate multipart parts (`proof`, `photos`) with
  separate allow-lists in `backend/core/storage.py` (`validate_proof_upload`,
  `validate_image_upload`) so a document can never be smuggled in as a photo or
  the reverse. `WebsiteLeadAttachment.is_public` (migration `d1e2f3a4b5c6`,
  default false) marks photos; proof and CV uploads stay private.
- **Public photo endpoint** — `GET /api/v1/public/opportunities/{id}/photos/{attachment_id}`
  streams a photo only when the listing is published *and* the attachment belongs
  to its lead *and* is public; otherwise the same 404 as a missing photo. Proof
  documents and CVs are never reachable, and `PublicOpportunityOut.photo_urls`
  only ever lists public photos. Regression: `tests/test_website_leads.py`
  (proof+photos, unpublished 404, proof never served, published shape).
- **Careers CV** — the form sends the file as the `cv` part; `submit_careers`
  reads `cv` (with `files` kept as a fallback) and validates it against
  `CV_CONTENT_TYPES` (PDF/DOC/DOCX, 10 MB), matching what the form advertises
  (item 14). Regression: `tests/test_website_leads.py`
  (`test_careers_accepts_the_advertised_cv_formats_and_rejects_images`).
- **Form hints** — `_field()` in `renderer.py` accepts `multiple`, per-field
  `label_ar`/`label_en` and `hint_ar`/`hint_en`, so the accepted formats and
  size limits sit next to each file control in the visitor's language.
- When adding a migration, update the single-head assertion in
  `tests/test_postgres.py`.

## Executions 01-03 — audit, financial workflow, header repair

- **Header nav is the flexible, scrollable row** — `.header-inner` is a
  `display:flex` row holding the brand, the 14 permission-gated `.nav-item`s and
  `.h-actions`. `.nav` must be `flex:1 1 auto; min-width:0; overflow-x:auto`
  (with `.h-actions` `flex:0 0 auto`); otherwise the items overflow and paint on
  top of the language switch / profile / Sign out at widths >1180px (the
  `overflow-x:auto` that previously existed only inside the `max-width:1180px`
  media query). Regression harness: a Playwright overflow/overlap sweep at
  1440/1024/768/390/360 in AR and EN. Fix: `frontend/styles.css` `.nav`,
  `.nav-item`, `.h-actions`.
- **Money is locale-aware, not always Arabic** — the Execution 02 financial view
  originally rendered the totals strip and row amounts with `finMoneyAr(...)`
  regardless of language, so English showed Arabic-Indic digits and `ر.س`. Use
  `finMoney(value)` (routes through `STATE.lang`); keep `finMoneyAr`/`finMoneyEn`
  only where both forms are needed side by side. Fix: `frontend/app.js`.
- **Roles & Permissions admin UX is catalogue-driven** — the admin "roles" tab
  (`renderAdminRoles`/`permEditor`/`renderPermGroups` in `frontend/app.js`) pulls
  `/api/v1/admin/permissions/catalogue` (bilingual name/description/category/
  action/danger) and renders grouped permissions, search, category chips,
  per-category select-all, enabled/total/visible counters, sensitive badges and
  unsaved-change tracking. The dynamic language switch (`setLang` →
  `refreshActiveView` → `renderAdminTab`) rebuilds it, so AR=RTL / EN=LTR. Do
  not hard-code permission names here; the backend catalogue is the source.
- **Financial summary workflow** — `backend/services/financial_service.py`
  (state machine DRAFT→SUBMITTED→APPROVED/CORRECTION_REQUIRED, corrections as
  new versions), `financial_calc.py` (Decimal-only; INCLUDED items are never
  double-counted; non-base currency rejected), `financial_reporting.py` (reads
  only `period.effective_version_id`, so two versions of a month are never
  summed). Migration `58ef167fa236` is additive (single head). Tests:
  `tests/test_financial.py`.
- **Spec source** — `Platform_Executive_Specifications_v1.docx` is not in the
  repo (only 14-byte placeholder stubs under `uploads/`); audit docs under
  `docs/audit/` cite the section/screen numbers they can verify from source.

