# SAFIR Holding — API Endpoint Coverage vs Specification

**Companion to:** `SAFIR_CURRENT_SYSTEM_AUDIT.md`, `SAFIR_SPECIFICATION_GAP_MATRIX.md`
**Commit audited:** `abfcd0de5f16640135a68fa6a03079988099857c` (baseline) +
`feature/safir-s26-s28-accounting-completion`
**Date:** 2026-10-14 (section 2 rewritten; the 2026-10-04 "missing" rows were stale)

> Every route below was enumerated from `backend/api/v1/*.py`. Each is permission-guarded
> server-side. Absence of a route means the module is unbuilt (see the gap matrix).

---

## 1. Existing routers and coverage

### auth (`/api/v1/auth`)
`POST /login`, `POST /refresh`, `POST /logout`, `GET /me` — ✅ complete (spec D11 login method still open).

### users & companies (`/api/v1`)
`GET /users/me/permissions`, `GET /users`, `PATCH /users/{id}`, `POST /users/{id}/…`,
`DELETE /users/{id}`, `POST /users`; `GET /companies`, `GET /companies/{id}`,
`POST /companies`, `PATCH /companies/{id}`; `GET /rbac/roles`, `POST /rbac/sync` — ✅ users;
✅ companies (a managed bilingual `Sector` catalogue exists; F-01 field set complete).

### admin (`/api/v1/admin`)
`GET/PATCH /holding`, `GET /holding/structure`, `GET /branding`, `POST/DELETE /branding/logo`,
`GET/POST/PATCH /ownerships`, `POST /ownerships/{id}/end`,
`GET/POST/PATCH /departments`, `GET /users`, `GET /roles`, `GET /roles/{code}`,
`POST /roles`, `PATCH /roles/{code}`, `PUT /roles/{code}/permissions`,
`GET /permissions`, `GET /permissions/catalogue`, `GET /audit-logs` — ✅ RBAC/org/branding/audit.
**Related routers (not under `/admin`):** leadership assessment and complaints live in
`confidential.py`; owner decisions, campaigns, advisory sessions, tasks and weekly reports
live in `operations.py`; employees/positions live in `hr.py`; opening balances and the
holding accounting surface live in `accounting.py`.

### dashboard (`/api/v1/dashboard`)
`GET /holding`, `GET /company/{company_id}`, `GET /indicator/{indicator}/sources`
— ✅ KPIs plus the AC-01 per-indicator drill-down to the source records (scoped,
never a copy).

### reports (`/api/v1/monthly-reports`)
`GET ""`, `GET /{id}`, `POST ""`, `PATCH /{id}`, `POST /{id}/submit`,
`POST /{id}/attachments`, `DELETE /{id}/attachments/{aid}`, `POST /{id}/financial-review`
— ✅; the versioned correction/return-with-note flow lives in `financial.py`
(`/periods`, `/summaries/{id}/submit|return|approve|correct`, bank-statement download).

### support (`/api/v1/support-requests`)
`GET ""`, `GET /{id}`, `POST ""`, `PATCH /{id}/status`, `PATCH /{id}/assign`,
`GET /{id}/comments`, `POST /{id}/comments` — ✅ including the design fields and the
direct-to-specialist delivery path (T03).

### documents (`/api/v1/documents`)
categories CRUD, list, `GET /expiry-summary`, `POST ""`, `GET/PATCH /{id}`,
`POST /{id}/archive`, `GET /{id}/download` — ✅.

### forms / workflows / submissions / approvals
full CRUD + versioning + publish/archive + steps/fields/requirements + approvals
— ✅ dynamic operations platform.

### notifications / integrations
`GET ""`, `GET /summary`, `POST /{id}/read`, `POST /read-all`, `POST /scan-documents`;
webhooks CRUD + deliveries — ✅.

### ai / analytics
`POST /ai/holding`, `POST /ai/company`, `GET /ai/insights`;
`GET /analytics/holding|operations|compliance|investments|briefing` — ✅ AI + analytics,
including the five-axis monthly brief (`operations.py` `/management-briefs`) and the
owner-only leadership-assessment AI (`confidential.py`, evidence-gap aware).

### leads (`/api/v1/leads`)
`GET ""`, `GET /opportunities`, `GET /stats`, `GET /{id}`, `PATCH /{id}` (assignment
included), `GET/POST /{id}/notes`, `POST /opportunities/{id}/review` — ✅ assignment,
manager/marketing note separation and opportunity review present. The *redistribution
history* rule is part of the unresolved D04 visibility decision and is deliberately not
invented here.

### website CMS (`/api/v1/website-cms`)
overview, settings, media, slides, pages (+publish/unpublish), menus, companies (+seed),
services, seo, revisions — ✅ Phase 11 complete.

### public (`/api/v1/public`)
contact/lead/opportunity/careers/group-service submissions, `GET /opportunities`,
`GET /website/media/{id}`, branding — ✅ Phase 10 complete.

---

## 2. Endpoint groups by spec screen (re-verified 2026-10-14)

> **Revision note.** The 2026-10-04 rows below this section claimed S04–S22 were
> unbuilt. That is no longer true: routers `hr.py`, `operations.py`,
> `accounting.py`, `confidential.py` and the extended `financial.py` now serve
> those screens, and each is permission-guarded server-side. The table is
> rewritten to the audited state; the old claim is retained only in git history.

| Spec area | Endpoints expected | Present |
|---|---|---|
| S04 Opening balances | list/create/update opening & carry-forward | ✅ `accounting.py` `/accounting/opening-balances` |
| S05 v2 financial summary | period/version create, send, return, correct, approve | ✅ `financial.py` (period → version → review actions) |
| S06 Special items | item CRUD with classification/inclusion | ✅ `financial.py` summary items |
| S07 Financial field config | field definition/revision CRUD | ✅ `forms.py` dynamic forms |
| S11 Employees | positions/employees/leaves/advances | ✅ `hr.py` |
| S12/S23 Assessments | assessment CRUD, criteria, leadership (owner-only) | ✅ `hr.py` + `confidential.py` (owner-only) |
| S14 Campaigns | campaign CRUD + results | ✅ `operations.py` `/campaigns` |
| S15 Complaints | create (marketing) / decide (owner) | ✅ `operations.py` `/complaints` + `confidential.py` |
| S17 Tasks | task CRUD/status/overdue | ✅ `operations.py` `/tasks` |
| S18 Weekly reports | draft/save/submit, ≤5 questions | ✅ `operations.py` `/weekly-reports` (+ `/weekly-reports/questions`) |
| S19 Advisory | advisor assignment, sessions, recommendations, monthly report | ✅ `operations.py` `/advisors`, `/advisory-sessions`, `/advisor-reports` |
| S20 Projects/opportunities | project/opportunity CRUD + states | ✅ `operations.py` `/projects` |
| S21 Executive brief | five-axis monthly brief | ✅ `operations.py` `/management-briefs` |
| S22 Owner decisions | topic/decision/directive CRUD + archive | ✅ `operations.py` `/owner-decisions` |
| S25 Notifications | preferences + delivery log (D11) | ✅ `notifications.py` `/notifications/preferences[/{event_type}]` |
| S26/S27/S28 Holding accounting | accounts, journals, invoices, receivables, parties, inter-company balances, assets, budgets, trial balance, KPIs, policies | ✅ `accounting.py` |
| D01 Policies | draft/approve/effective registry | ✅ `accounting.py` `/accounting/policies` |
| D02 KPI targets | definitions, activation, evaluations, sources | ✅ `accounting.py` `/accounting/kpis/*` |

---

## 3. API correctness / security observations

- ✅ All service entry points call `require_permission` / `require_any_permission`.
- ✅ Scoped repositories apply company scope at query time (no post-fetch check).
- ✅ Out-of-scope ids return 404 (`NotFoundError`), not 403.
- ✅ Login rate-limited; failed login audited; account enumeration defended.
- 🟡 `POST /monthly-reports/{id}/submit` has no explicit idempotency key; re-submit is
  blocked only by the draft-only guard. Consider an idempotency guard when versions land (T07).
- 🟡 Report list returns **all** reports for holding-wide roles with no pagination; add
  paging before data volume grows.
- 🟡 No endpoint exposes a bank-transfer action (correct, must remain so).
