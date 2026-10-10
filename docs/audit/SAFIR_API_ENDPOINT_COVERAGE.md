# SAFIR Holding — API Endpoint Coverage vs Specification

**Companion to:** `SAFIR_CURRENT_SYSTEM_AUDIT.md`, `SAFIR_SPECIFICATION_GAP_MATRIX.md`
**Commit audited:** `cebde883fd5d1061e20fe70d756fbc61e6047633`
**Date:** 2026-10-04

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
🟡 companies (no Sector entity, F-01 field set incomplete).

### admin (`/api/v1/admin`)
`GET/PATCH /holding`, `GET /holding/structure`, `GET /branding`, `POST/DELETE /branding/logo`,
`GET/POST/PATCH /ownerships`, `POST /ownerships/{id}/end`,
`GET/POST/PATCH /departments`, `GET /users`, `GET /roles`, `GET /roles/{code}`,
`POST /roles`, `PATCH /roles/{code}`, `PUT /roles/{code}/permissions`,
`GET /permissions`, `GET /permissions/catalogue`, `GET /audit-logs` — ✅ RBAC/org/branding/audit.
**Missing routes:** leadership assessment, owner decisions, opening balances, employees,
campaigns, complaints, advisory sessions, holding accounting.

### dashboard (`/api/v1/dashboard`)
`GET /holding`, `GET /company/{company_id}` — 🟡 KPIs only; no per-metric drill-down.

### reports (`/api/v1/monthly-reports`)
`GET ""`, `GET /{id}`, `POST ""`, `PATCH /{id}`, `POST /{id}/submit`,
`POST /{id}/attachments`, `DELETE /{id}/attachments/{aid}`, `POST /{id}/financial-review`
— 🟡 no version/correction/return-with-note; no bank statement.

### support (`/api/v1/support-requests`)
`GET ""`, `GET /{id}`, `POST ""`, `PATCH /{id}/status`, `PATCH /{id}/assign`,
`GET /{id}/comments`, `POST /{id}/comments` — 🟡 generic; no design lifecycle/delivery.

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
`GET /analytics/holding|operations|compliance|investments|briefing` — 🟡 AI + analytics
present; no leadership-assessment AI, no five-axis monthly brief.

### leads (`/api/v1/leads`)
`GET ""`, `GET /stats`, `GET /{id}`, `PATCH /{id}`, `POST /opportunities/{id}/review`
— 🟡 assignment/notes present; redistribution/history (D04) and full pipeline (D03) open.

### website CMS (`/api/v1/website-cms`)
overview, settings, media, slides, pages (+publish/unpublish), menus, companies (+seed),
services, seo, revisions — ✅ Phase 11 complete.

### public (`/api/v1/public`)
contact/lead/opportunity/careers/group-service submissions, `GET /opportunities`,
`GET /website/media/{id}`, branding — ✅ Phase 10 complete.

---

## 2. Missing endpoint groups (by spec screen)

| Spec area | Endpoints expected | Present |
|---|---|---|
| S04 Opening balances | list/create/update opening & carry-forward | ❌ |
| S05 v2 financial summary | period/version create, send, return, correct, approve | ❌ (only single report) |
| S06 Special items | item CRUD with classification/inclusion | ❌ |
| S07 Financial field config | field definition/revision CRUD | ❌ (generic forms only) |
| S11 Employees | positions/employees/leaves/advances | ❌ |
| S12/S23 Assessments | assessment CRUD, criteria, leadership (owner-only) | ❌ |
| S14 Campaigns | campaign CRUD + results | ❌ |
| S15 Complaints | create (marketing) / decide (owner) | ❌ |
| S17 Tasks | task CRUD/status/overdue | ❌ |
| S18 Weekly reports | draft/save/submit, ≤5 questions | ❌ |
| S19 Advisory | advisor assignment, sessions, recommendations, monthly report | ❌ |
| S20 Projects/opportunities | project/opportunity CRUD + states | ❌ |
| S21 Executive brief | five-axis monthly brief | ❌ |
| S22 Owner decisions | topic/decision/directive CRUD + archive | ❌ |
| S26/S27/S28 Holding accounting | accounts, journals, invoices, receivables, assets, budgets, trial balance | ❌ 🔒 |

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
