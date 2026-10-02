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
`test_dashboard`, `test_ai`, `test_admin`, `test_schemas`.

## Known gaps (Phase 1 audit)

These are intentionally not yet built; add them in a later phase rather than
papering over them in tests:

- No `PATCH /users/{id}` or `GET /users` list endpoint (deactivation is DB-level only).
- No `PATCH /companies/{id}` or company access grant/revoke endpoints.
- `AI_PROVIDER` is configurable but only `none` is implemented.
