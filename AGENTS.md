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

## Frontend live hydration

`frontend/index.html` ships curated demo figures; `frontend/app.js` replaces
them with live API data when the page is served by the backend. The bridge is
opt-in per element, so a section that is not wired (or a request that fails)
keeps its demo content rather than blanking out.

Hooks the markup must keep for hydration to work:

- `body[data-api]` - backend origin. Empty string means same origin, which is
  the case when FastAPI serves `frontend/`. `?token=`, `?year=`, `?month=`
  query params supply auth and the reporting period.
- `[data-kpi="<name>"]` - KPI tiles, hub total, counts and deltas
  (`total_revenue`, `net_delta`, `net_margin`, `insights_count`, and so on).
- `#aiAnswer` + `#aiAnswerBody` - the Holding AI executive summary block.
- `#insightsList`, `#supportBody`, `.rep-grid`, `.subs`, `.ov-card .card-body`
  - containers whose innerHTML the bridge replaces wholesale.

Anything a live API returns is HTML-escaped before insertion (the AI answer
included), since a real LLM provider could otherwise emit markup.
