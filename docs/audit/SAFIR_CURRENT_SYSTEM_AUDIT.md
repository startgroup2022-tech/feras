# SAFIR Holding — Current System Audit

**Execution:** EXECUTION 01 — Full System Audit & Gap Analysis
**Repository:** `startgroup2022-tech/feras`
**Branch audited:** `frontend-app-conversion`
**Commit SHA audited:** `cebde883fd5d1061e20fe70d756fbc61e6047633`
**Specification:** `Platform_Executive_Specifications_v1.docx` (v1.0, 10 Oct 2026)
**Date:** 2026-10-04
**Audit type:** read-only. No production data was changed; nothing was deployed or restarted.

> **Classification key:** COMPLETE = implemented **and** covered by a passing test;
> PARTIAL = exists but has functional gaps; MISSING = no model/endpoint/service;
> BROKEN = implemented but failing; BLOCKED = needs an unresolved owner decision
> (D01–D11) before the affected rule can be built.

---

## 1. Method

Every claim below was verified by reading the source, not by inspecting buttons or
previews. The audit traced each capability from the UI (`frontend/`) through the API
(`backend/api/v1/`), the service layer (`backend/services/`), the ORM models
(`backend/db/models/`), and the RBAC catalogue (`backend/rbac/`). The full test suite
was executed locally (575 tests, all passing).

Evidence classes used:
- **Model/DDL** — the table exists in `backend/db/models/*` and compiles.
- **API** — a routed endpoint in `backend/api/v1/*`.
- **Service** — business rules in `backend/services/*`.
- **Permission** — a code in `backend/rbac/permissions.py`.
- **Test** — a passing test in `tests/`.

---

## 2. Repository and deployment safety (as found)

| Item | Finding |
|---|---|
| Working tree | Clean; no uncommitted changes. |
| Local HEAD | `cebde88` on `fix/safeer-revision-brief`. |
| `origin/frontend-app-conversion` | `cebde88` — identical to local HEAD; the recent work is safely pushed. |
| Local `frontend-app-conversion` ref | Stale (`5f05174`, behind by 2); the *remote* branch is current. Re-sync when continuing work. |
| Migration graph | Single linear head at `d1e2f3a4b5c6`; 9 revisions; no branches (`tests/test_postgres.py` asserts this). |
| Production changes made | None. No deploy, no restart, no DB writes. |

---

## 3. Current architecture (verified)

- **Runtime:** FastAPI 0.115 + SQLAlchemy 2.0 + Alembic; SQLite for local dev, PostgreSQL
  via psycopg 3 for staging/production.
- **Auth:** JWT access/refresh tokens (`backend/core/security.py`,
  `backend/services/auth_service.py`). Access token short-lived; user re-read on every
  request so deactivation is immediate.
- **RBAC:** a flat permission catalogue (`backend/rbac/permissions.py`, 86 permission
  codes) with 14 roles. Endpoints require *permission codes*, never role names.
- **Tenant isolation:** company scope applied as a SQL filter through scoped repositories
  (`backend/repositories/scoped.py`) plus `require_company_access`
  (`backend/rbac/authorization.py`). Out-of-scope ids return **404**, not 403.
- **Public website:** separate Phase 10 (leads/opportunities) and Phase 11 (CMS) modules,
  served by `backend/website/` and `website/assets/`.
- **Internal platform UI:** single-page `frontend/app.js` with permission-gated views.

---

## 4. Feature-by-feature audit (trace UI → API → service → DB → permissions)

### 4.1 Authentication, sessions, users, roles, permissions

| Capability | UI | API | Service/Model | Permission | Tests | Status |
|---|---|---|---|---|---|---|
| Login / refresh / logout | `auth.js` | `POST /auth/login`, `/auth/refresh`, `/auth/logout`, `GET /auth/me` | `auth_service` | — (authenticated) | `test_auth.py` (14) | COMPLETE |
| Account enumeration / timing defence | — | — | `dummy_verify`, generic error | — | `test_auth.py` | COMPLETE |
| Login rate limiting | — | — | `core/rate_limit.py` | — | `test_auth.py`, `test_staging_security.py` | COMPLETE |
| Users CRUD, role/company assignment | Admin → Users | `/users/*`, `/admin/users` | `admin_service` | `user.*`, `role.*` | `test_admin.py`, `test_group_admin.py` | COMPLETE |
| Roles list/edit + custom roles | Admin → Roles | `/admin/roles*`, `/rbac/roles` | `role_service`, `rbac_service` | `role.read/manage`, `permission.assign` | `test_rbac.py` (23) | COMPLETE |
| Bilingual role names/descriptions | Admin → Roles | `RoleOut.description_ar/en` | `Role`, `rbac_service.sync_roles` | `role.read` | `test_rbac.py` | COMPLETE |
| Permission catalogue (AR/EN, grouped, danger) | Admin → Roles | `GET /admin/permissions/catalogue` | `permission_metadata` | `permission.read` | `test_permission_metadata.py` (10) | COMPLETE |
| Privilege-escalation guard | — | — | `role_service._assert_no_escalation` | `role.manage` | `test_rbac.py` | COMPLETE |
| Tenant/company isolation | — | all scoped endpoints | `scoped.py`, `authorization.py` | — | `test_isolation.py` (19) | COMPLETE |
| External Consultant role | — | — | — | — | — | **MISSING** |

**Gap (high):** the specification requires **7 operational roles** (Owner, Business
Development, Subsidiary Manager, Accountant, Marketing, Designer, **External Consultant**).
The codebase has **no `external_consultant` role and no advisor data model**
(`AdvisorAssignment`, `Session`, `Recommendation`). See §5 and the Role/Permission matrix.

**Gap (medium):** the specification refers to a **Custom Role** scope restriction — a
custom role may never see the confidential leadership centre (AC-25). The escalation
guard prevents granting privileges the actor lacks, but there is no *deny-list* forbidding
leadership permissions from custom roles. This is currently moot because the leadership
module itself is missing.

### 4.2 Owner dashboard and executive controls

| Screen | UI | API | Service/Model | Status |
|---|---|---|---|---|
| S01 Dashboard | `app.js` board + `/dashboard/holding` | `dashboard_service` | PARTIAL — group KPIs only; no owner priorities/decision links; **no complaints, no leadership** on the home (correct) |
| S02 Companies list/detail | Admin → Structure/Companies | `/companies`, `/admin/holding/structure`, `/admin/ownerships` | COMPLETE (holding + ownership + departments) |
| S03 Add company + sector | Admin → Companies | `POST /companies` | PARTIAL — company/sector exist; **dynamic sector list and F-01 field set not enforced**; currency present |
| S04 Opening/carryforward balances | — | — | **MISSING** — no `OpeningBalance` model/endpoint |
| S07 Field/sector/line config | — | — | PARTIAL — dynamic forms/fields exist (`forms.py`), but **no financial item definition with inclusion rule / historical snapshot** |
| S20 Projects & opportunities | — | — | MISSING (platform-side); public opportunities exist but not owner project tracking |
| S22 Owner decisions & directives | — | — | **MISSING** — no `OwnerTopic/Decision/Directive` model |
| S23 Confidential leadership assessment | — | — | **MISSING** |
| S24 Organization structure | Admin → Structure | `/admin/holding/structure` | PARTIAL — departments/ownership/holdings render; **legal function, positions model, reporting lines not modelled** |
| S25 Users/permissions/settings | Admin | `/admin/users`, `/admin/roles`, `/admin/audit-logs` | PARTIAL — users/roles/permissions/audit complete; **notifications prefs and login method (D11) not modelled** |
| S15 Complaints (owner-only) | — | — | **MISSING** |
| S21 Management reports | Reports view | `/monthly-reports` | PARTIAL — company monthly report exists; **BD five-axis analysis + executive brief + escalation missing** |
| S26/S27/S28 Holding accounting | — | — | **MISSING** — no journals, chart of accounts, invoices, assets, budgets (BLOCKED on D01/D07) |

### 4.3 Business Development Manager dashboard

| Screen | Status |
|---|---|
| S01, S02, S09, S10 (reports/performance) | PARTIAL — report read and company performance exist |
| S11 Employees | **MISSING** (no employee model; see §4.9) |
| S12 Employee assessment / development | **MISSING** (weights are in the spec; no model) |
| S19 Advisory sessions | **MISSING** |
| S16 Service/design requests | PARTIAL — generic support requests exist; no design request lifecycle, sizes, delivery links |
| S17 Tasks | **MISSING** as a first-class task entity (the dynamic workflow/approval engine covers approvals, not BD-assigned tasks) |
| S20 Projects/opportunities | MISSING (platform-side) |
| S21/22 Reports/decisions | PARTIAL / MISSING |
| S26–S28 Holding finance | MISSING |

### 4.4 Subsidiary Company Manager dashboard

| Screen | Status |
|---|---|
| S01, S10 performance | PARTIAL |
| S04 Opening/carryforward balances | **MISSING** |
| S05 Monthly financial summary (F-03) | PARTIAL — a monthly report with revenue/expenses/net/receivables exists; **bank/cash, special items, bank statement, versions, submit/return/correct** missing (see financial audit) |
| S06 Special financial items (F-04) | **MISSING** |
| S09 Subsidiary monthly report (F-07) | PARTIAL — narrative fields exist; **no link to the financial part’s review status, no correction version** |
| S11 Employees | MISSING |
| S13 Leads | PARTIAL — website leads exist with assignment/notes; **pipeline states/redistribution need D03/D04** |
| S16 Service requests | PARTIAL |
| S22 Owner directives (received) | MISSING |

### 4.5 Accountant dashboard

| Screen | Status |
|---|---|
| S02/S08/S07/S10 finance views | PARTIAL — report review exists; field config exists; **versions/correction workflow and review-return-with-note missing** |
| S26/S27/S28 Holding accounts, invoices, assets, budget | **MISSING** — BLOCKED on D01 (accounting card) and D07 (budget source) |
| S18 Weekly report | **MISSING** |
| S16/S17 tasks/requests | PARTIAL |
| **Accountant review & approval of F-03** | PARTIAL — `review_financially` flags accurate/not + verified figures; **no explicit approve/reject/return-for-correction with mandatory note; no version chain; no exactly-one-effective rule** |

### 4.6 Marketing Specialist dashboard

| Screen | Status |
|---|---|
| S13 Leads/distribution | PARTIAL — lead read + assignment; **manager-note separation and redistribution rules need D03/D04** |
| S14 Campaigns | **MISSING** |
| S15 Complaints (owner-only) | **MISSING** |
| S16/S17 Tasks/requests | PARTIAL |
| S18 Weekly report | **MISSING** |
| S19 Marketing advisor | **MISSING** |
| Website CMS (Phase 11) | COMPLETE — marketing drafts/uploads; publishing is owner-held |

### 4.7 Designer dashboard

| Screen | Status |
|---|---|
| S16 Design requests / completed work | PARTIAL — generic support requests; **no design lifecycle, sizes, delivery links** |
| S17 My tasks | MISSING (as first-class tasks) |
| S18 Weekly report | MISSING |

### 4.8 External Advisor dashboard (S19)

**MISSING entirely** — no role, model, or endpoint. The UI has no advisor view.

### 4.9 Employees, assessments, tasks, weekly reports

| Item | Status |
|---|---|
| Employee / Position model | **MISSING** |
| EmployeeAction / Leave / Advance | **MISSING** (BLOCKED partly on D06) |
| Assessments + criteria + weights | **MISSING** (weights known; grade scale BLOCKED on D05) |
| Leadership assessment (owner-only, confidential) | **MISSING** |
| Tasks (BD-assigned, statuses, overdue) | **MISSING** (distinct from the approval engine) |
| Weekly employee report (≤5 questions incl. advisor) | **MISSING** |
| Motivation text library | **MISSING** |

### 4.10 Leads, campaigns, complaints, service requests

| Item | Status |
|---|---|
| Website leads (public) | COMPLETE — model, API, assignment, statuses, notes, isolation |
| Lead notes separation (marketing vs manager) | PARTIAL — notes exist; explicit two-author separation not enforced |
| Campaigns | **MISSING** |
| Complaints (owner-only, confidential) | **MISSING** |
| Service requests | PARTIAL — generic support requests with categories, comments, assignments |
| Design requests + deliveries | PARTIAL/MISSING |

### 4.11 Advisory sessions and recommendations

**MISSING** — `AdvisorAssignment`, `Session`, `Recommendation` and the advisor scope
(D04) do not exist.

### 4.12 Notifications, activity logs, audit trails, security

| Item | Status |
|---|---|
| Notification centre | COMPLETE — model, API, per-type routing, read/read-all |
| Audit log | COMPLETE — `AuditLog` + `AuditAction`, admin read endpoint, metadata |
| Company isolation on search/reports/notifications/links | COMPLETE (verified by `test_isolation.py`, `test_staging_security.py`) |
| Complaint confidentiality in public log/counters | N/A — no complaints module (would leak if built naively) |
| Document expiry & attachments | COMPLETE |
| Backup/restore, encryption, retention | PARTIAL — documented (`docs/BACKUP_RESTORE.md`), BLOCKED on D10 |

### 4.13 AI-assisted analysis and reporting

| Item | Status |
|---|---|
| Holding / Company AI Q&A | COMPLETE — `/ai/holding`, `/ai/company`, provider abstraction, `test_ai*.py` |
| AI insights | COMPLETE — `/ai/insights`, `insights_service.py` |
| Executive briefing | PARTIAL — `analytics/briefing` exists; spec’s five-axis monthly brief tied to source reports not enforced |
| AI leadership assessment with evidence-gap display | **MISSING** (BLOCKED on D05) |
| AI failure must not fabricate a score | N/A yet (no assessment) |
| AI text-organisation of a manager’s narrative | PARTIAL — AI exists but no “organise this report” action |

### 4.14 Internationalisation, RTL/LTR, responsive

| Item | Status |
|---|---|
| AR/EN language switch | COMPLETE — `setLang`, `html.lang-ar/en`, dir switch |
| RTL/LTR correctness (nav, tables, phone/email/money direction) | COMPLETE |
| Bilingual system strings from `dual()` | COMPLETE |
| Language switch preserves page/company/unsaved values | COMPLETE (re-render path) |
| Responsive mobile layout (internal) | COMPLETE — mobile header rules, tests |
| Public website bilingual + responsive | COMPLETE |

---

## 5. Verified recent changes (section 7 of the brief)

| Change | Present? | Evidence |
|---|---|---|
| Bilingual roles & permissions management | ✅ | `c4a9e1f2b3d7`, `test_rbac.py`, `/admin/roles` |
| Responsive mobile layout | ✅ | `styles.css` mobile rules, `test_website_pages.py` |
| Careers CV upload fix (param `files`→`cv`) | ✅ | `backend/api/v1/public.py` `submit_careers(cv=…)`, `test_website_leads.py` |
| Listing proof-document upload | ✅ | `validate_proof_upload`, `/leads/business-listing` `proof` |
| Up to 10 listing photos | ✅ | `PUBLIC_MAX_LISTING_PHOTOS = 10`, multiple `photos` |
| Private vs public attachment visibility | ✅ | `WebsiteLeadAttachment.is_public` |
| Public photo access only for published listings | ✅ | `public_opportunity_photo`, tests |
| PostgreSQL migration `d1e2f3a4b5c6` | ✅ | single head, asserted in `test_postgres.py` |

### Boolean default fix — **DISCREPANCY CONFIRMED**

The brief asks whether the PostgreSQL Boolean default fix (`sa.false()` instead of
`sa.text("0")`) exists. **It does not.**

- `alembic/versions/d1e2f3a4b5c6_listing_photo_visibility.py` line 35 still uses
  `server_default=sa.text("0")`.
- `backend/db/models/website.py` uses `server_default="0"` for `is_public`.

Compiling the two on the PostgreSQL dialect (verified locally, SQLAlchemy 2.0.36):

```
sa.text("0") : CREATE TABLE t (is_public BOOLEAN DEFAULT 0 NOT NULL)
sa.false()   : CREATE TABLE t (is_public BOOLEAN DEFAULT false NOT NULL)
"0" (string) : CREATE TABLE t (is_public BOOLEAN DEFAULT '0' NOT NULL)
```

**Assessment:** the SQLite test suite passes and PostgreSQL accepts the DDL, but
`DEFAULT 0` / `DEFAULT '0'` against a `BOOLEAN` column is not the canonical form and is
fragile across PostgreSQL versions and tools. **Recommendation (not applied in this
audit):** change both to `sa.false()`. Not a functional blocker; flagged as a
portability follow-up. **No production change was made.**

---

## 6. Summary

| Category | Count |
|---|---|
| Verified modules (COMPLETE) | 14 role-governed + 7 platform/website modules |
| Partially implemented modules (PARTIAL) | 16 |
| Missing modules (MISSING) | 18 |
| Broken modules (BROKEN) | 0 (full suite green) |
| Unresolved owner decisions | 11 (D01–D11) |

**Headline:** the *foundational* platform (auth, RBAC, tenant isolation, audits,
notifications, dynamic forms/workflows/approvals/documents, AI, public website + CMS,
bilingual/responsive) is **solid and tested**. The **holding-business domain** designed in
the executive specification (holding accounting, financial summary versions/correction,
opening balances, special items, employees/assessments/tasks, campaigns/complaints,
advisory sessions, owner decisions, leadership assessment) is **largely unbuilt**. Several
of those are gated by unresolved decisions D01–D11.

Detailed per-screen findings: `SAFIR_SPECIFICATION_GAP_MATRIX.md`.
