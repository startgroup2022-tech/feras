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
- Responsive: the 1920×1080 `.stage` scales down; at ≤820px the stage reflows
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
